import json
from datetime import datetime

from src.domain.interfaces.persistence import IProjectRepository, ITranslationRegionRepository, IGlossaryRepository
from src.domain.models.enums import ExtractionMethod, FitStatus, RegionStatus, RegionType
from src.domain.models.project import Project
from src.domain.models.region import TranslationRegion
from src.domain.value_objects.extraction import FragmentGranularity, SourceFragment
from src.domain.value_objects.geometry import Rect
from src.infrastructure.persistence.database import Database


from src.domain.interfaces.persistence import IUnitOfWork
from src.infrastructure.persistence.translation_memory_repository import SqliteTranslationMemoryRepository

class SqliteUnitOfWork(IUnitOfWork):
    def __init__(self, db: Database):
        self.db = db
        self._conn_ctx = None

    def __enter__(self):
        self._conn_ctx = self.db.transaction()
        self._conn_ctx.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._conn_ctx.__exit__(exc_type, exc_val, exc_tb)

    @property
    def region_repository(self):
        return SqliteTranslationRegionRepository(self.db)

    @property
    def translation_memory_repository(self):
        return SqliteTranslationMemoryRepository(self.db)

class SqliteProjectRepository(IProjectRepository):
    def __init__(self, db: Database):
        self.db = db

    def save(self, project: Project) -> None:
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO project 
                (id, name, pdf_path, pdf_sha256, pdf_size, pdf_page_count, last_viewed_page, created_at, updated_at, active_glossary_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    pdf_path=excluded.pdf_path,
                    pdf_sha256=excluded.pdf_sha256,
                    pdf_size=excluded.pdf_size,
                    pdf_page_count=excluded.pdf_page_count,
                    last_viewed_page=excluded.last_viewed_page,
                    updated_at=excluded.updated_at,
                    active_glossary_id=excluded.active_glossary_id
            """,
                (
                    project.id,
                    project.name,
                    project.pdf_path,
                    project.pdf_sha256,
                    project.pdf_size,
                    project.pdf_page_count,
                    project.last_viewed_page,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                    project.active_glossary_id,
                ),
            )

    def get(self, project_id: str) -> Project | None:
        with self.db.transaction() as conn:
            cursor = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,))
            row = cursor.fetchone()
            if row:
                return Project(
                    id=row["id"],
                    name=row["name"],
                    pdf_path=row["pdf_path"],
                    pdf_sha256=row["pdf_sha256"],
                    pdf_size=row["pdf_size"],
                    pdf_page_count=row["pdf_page_count"],
                    last_viewed_page=row["last_viewed_page"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    active_glossary_id=row["active_glossary_id"] if "active_glossary_id" in row.keys() else None,
                )
            return None


class SqliteTranslationRegionRepository(ITranslationRegionRepository):
    def __init__(self, db: Database):
        self.db = db

    def _serialize_source_fragments(self, fragments: list[SourceFragment] | None) -> str:
        if fragments is None:
            return json.dumps({"version": 1, "fragments": []})

        serialized_fragments = []
        for f in fragments:
            serialized_fragments.append(
                {
                    "text": f.text,
                    "bbox": [f.bbox.x0, f.bbox.y0, f.bbox.x1, f.bbox.y1],
                    "granularity": f.granularity.value,
                    "block_index": f.block_index,
                    "line_index": f.line_index,
                    "span_index": f.span_index,
                    "raw_font_name": f.raw_font_name,
                    "font_size": f.font_size,
                    "font_color": f.font_color,
                    "font_flags_raw": f.font_flags_raw,
                    "is_bold": f.is_bold,
                    "is_italic": f.is_italic,
                    "is_serif": f.is_serif,
                    "is_monospace": f.is_monospace,
                }
            )

        return json.dumps({"version": 1, "fragments": serialized_fragments})

    def _deserialize_source_fragments(self, json_str: str | None) -> list[SourceFragment] | None:
        if not json_str:
            return None

        data = json.loads(json_str)
        version = data.get("version", 1)
        if version != 1:
            raise ValueError(f"Unknown source_fragments JSON version: {version}")

        fragments = []
        for f_data in data.get("fragments", []):
            bbox = Rect(f_data["bbox"][0], f_data["bbox"][1], f_data["bbox"][2], f_data["bbox"][3])
            frag = SourceFragment(
                text=f_data["text"],
                bbox=bbox,
                granularity=FragmentGranularity(f_data["granularity"]),
                block_index=f_data["block_index"],
                line_index=f_data["line_index"],
                span_index=f_data["span_index"],
                raw_font_name=f_data["raw_font_name"],
                font_size=f_data["font_size"],
                font_color=f_data["font_color"],
                font_flags_raw=f_data["font_flags_raw"],
                is_bold=f_data["is_bold"],
                is_italic=f_data["is_italic"],
                is_serif=f_data["is_serif"],
                is_monospace=f_data["is_monospace"],
            )
            fragments.append(frag)

        return fragments

    def save(self, region: TranslationRegion) -> None:
        s_bbox_x0 = region.source_bbox.x0 if region.source_bbox else None
        s_bbox_y0 = region.source_bbox.y0 if region.source_bbox else None
        s_bbox_x1 = region.source_bbox.x1 if region.source_bbox else None
        s_bbox_y1 = region.source_bbox.y1 if region.source_bbox else None

        source_fragments_json = self._serialize_source_fragments(region.source_fragments)
        created_at_str = region.created_at.isoformat() if region.created_at else None
        updated_at_str = region.updated_at.isoformat() if region.updated_at else None

        translated_blocks_json = json.dumps(region.translated_blocks) if region.translated_blocks is not None else None
        translation_options_json = json.dumps(region.translation_options) if region.translation_options is not None else None

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO translation_region 
                (id, project_id, page_id, selection_x0, selection_y0, selection_x1, selection_y1,
                 source_bbox_x0, source_bbox_y0, source_bbox_x1, source_bbox_y1,
                 source_text, translated_text, region_type, status, extraction_method, fit_status,
                 source_fragments, created_at, updated_at, is_manually_edited,
                 translation_engine, translation_engine_version, target_font_size, target_font_family,
                 target_alignment, target_line_height, fit_scale,
                 translation_model, translated_blocks, prompt_template_version,
                 translation_options, glossary_id, glossary_revision, translation_revision,
                 reviewed_translation_revision, approved_translation_revision, reviewed_at, approved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    selection_x0=excluded.selection_x0,
                    selection_y0=excluded.selection_y0,
                    selection_x1=excluded.selection_x1,
                    selection_y1=excluded.selection_y1,
                    source_bbox_x0=excluded.source_bbox_x0,
                    source_bbox_y0=excluded.source_bbox_y0,
                    source_bbox_x1=excluded.source_bbox_x1,
                    source_bbox_y1=excluded.source_bbox_y1,
                    source_text=excluded.source_text,
                    translated_text=excluded.translated_text,
                    region_type=excluded.region_type,
                    status=excluded.status,
                    extraction_method=excluded.extraction_method,
                    fit_status=excluded.fit_status,
                    source_fragments=excluded.source_fragments,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    is_manually_edited=excluded.is_manually_edited,
                    translation_engine=excluded.translation_engine,
                    translation_engine_version=excluded.translation_engine_version,
                    target_font_size=excluded.target_font_size,
                    target_font_family=excluded.target_font_family,
                    target_alignment=excluded.target_alignment,
                    target_line_height=excluded.target_line_height,
                    fit_scale=excluded.fit_scale,
                    translation_model=excluded.translation_model,
                    translated_blocks=excluded.translated_blocks,
                    prompt_template_version=excluded.prompt_template_version,
                    translation_options=excluded.translation_options,
                    glossary_id=excluded.glossary_id,
                    glossary_revision=excluded.glossary_revision,
                    translation_revision=excluded.translation_revision,
                    reviewed_translation_revision=excluded.reviewed_translation_revision,
                    approved_translation_revision=excluded.approved_translation_revision,
                    reviewed_at=excluded.reviewed_at,
                    approved_at=excluded.approved_at
            """,
                (
                    region.id,
                    region.project_id,
                    region.page_id,
                    region.selection_rect.x0,
                    region.selection_rect.y0,
                    region.selection_rect.x1,
                    region.selection_rect.y1,
                    s_bbox_x0,
                    s_bbox_y0,
                    s_bbox_x1,
                    s_bbox_y1,
                    region.source_text,
                    region.translated_text,
                    region.region_type.name,
                    region.status.name,
                    region.extraction_method.name,
                    region.fit_status.name,
                    source_fragments_json,
                    created_at_str,
                    updated_at_str,
                    1 if region.is_manually_edited else 0,
                    region.translation_engine,
                    region.translation_engine_version,
                    region.target_font_size,
                    region.target_font_family,
                    region.target_alignment,
                    region.target_line_height,
                    region.fit_scale,
                    region.translation_model,
                    translated_blocks_json,
                    region.prompt_template_version,
                    translation_options_json,
                    region.glossary_id,
                    region.glossary_revision,
                    region.translation_revision,
                    region.reviewed_translation_revision,
                    region.approved_translation_revision,
                    region.reviewed_at.isoformat() if region.reviewed_at else None,
                    region.approved_at.isoformat() if region.approved_at else None,
                ),
            )

    def _row_to_region(self, row: dict) -> TranslationRegion:
        source_bbox = None
        if row["source_bbox_x0"] is not None:
            source_bbox = Rect(
                x0=row["source_bbox_x0"],
                y0=row["source_bbox_y0"],
                x1=row["source_bbox_x1"],
                y1=row["source_bbox_y1"],
            )

        source_fragments = self._deserialize_source_fragments(row.get("source_fragments"))

        created_at = None
        if row.get("created_at"):
            created_at = datetime.fromisoformat(row["created_at"])

        updated_at = None
        if row.get("updated_at"):
            updated_at = datetime.fromisoformat(row["updated_at"])

        translated_blocks = None
        if row.get("translated_blocks"):
            translated_blocks = json.loads(row["translated_blocks"])

        translation_options = None
        if row.get("translation_options"):
            translation_options = json.loads(row["translation_options"])

        return TranslationRegion(
            id=row["id"],
            project_id=row["project_id"],
            page_id=row["page_id"],
            selection_rect=Rect(
                x0=row["selection_x0"],
                y0=row["selection_y0"],
                x1=row["selection_x1"],
                y1=row["selection_y1"],
            ),
            source_bbox=source_bbox,
            source_fragments=source_fragments,
            source_text=row["source_text"],
            translated_text=row["translated_text"],
            region_type=RegionType[row["region_type"]],
            status=RegionStatus[row["status"]],
            extraction_method=ExtractionMethod[row["extraction_method"]],
            fit_status=FitStatus[row["fit_status"]],
            created_at=created_at,
            updated_at=updated_at,
            is_manually_edited=bool(row.get("is_manually_edited", 0)),
            translation_engine=row.get("translation_engine"),
            translation_engine_version=row.get("translation_engine_version"),
            target_font_size=row.get("target_font_size"),
            target_font_family=row.get("target_font_family"),
            target_alignment=row.get("target_alignment"),
            target_line_height=row.get("target_line_height"),
            fit_scale=row.get("fit_scale"),
            translation_model=row.get("translation_model"),
            translated_blocks=translated_blocks,
            prompt_template_version=row.get("prompt_template_version"),
            translation_options=translation_options,
            glossary_id=row.get("glossary_id"),
            glossary_revision=row.get("glossary_revision"),
            translation_revision=row.get("translation_revision"),
            reviewed_translation_revision=row.get("reviewed_translation_revision"),
            approved_translation_revision=row.get("approved_translation_revision"),
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]) if row.get("reviewed_at") else None,
            approved_at=datetime.fromisoformat(row["approved_at"]) if row.get("approved_at") else None,
        )

    def get(self, region_id: str) -> TranslationRegion | None:
        with self.db.transaction() as conn:
            cursor = conn.execute("SELECT * FROM translation_region WHERE id = ?", (region_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_region(dict(row))
            return None

    def delete(self, region_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM translation_region WHERE id = ?", (region_id,))

    def get_by_page(self, project_id: str, page_id: int) -> list[TranslationRegion]:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT * FROM translation_region WHERE project_id = ? AND page_id = ?",
                (project_id, page_id),
            )
            return [self._row_to_region(dict(row)) for row in cursor.fetchall()]

    def get_all(self, project_id: str) -> list[TranslationRegion]:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT * FROM translation_region WHERE project_id = ?",
                (project_id,),
            )
            return [self._row_to_region(dict(row)) for row in cursor.fetchall()]

    def count(self, project_id: str) -> int:
        with self.db.transaction() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM translation_region WHERE project_id = ?",
                (project_id,),
            )
            return cursor.fetchone()[0]


class SqliteGlossaryRepository(IGlossaryRepository):
    def __init__(self, db: Database):
        self.db = db

    def save(self, glossary: 'Glossary') -> None:
        from src.domain.models.glossary import Glossary
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO glossary 
                (id, project_id, name, revision, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    revision=excluded.revision,
                    updated_at=excluded.updated_at
                """,
                (
                    glossary.id,
                    glossary.project_id,
                    glossary.name,
                    glossary.revision,
                    (glossary.created_at or datetime.now()).isoformat(),
                    (glossary.updated_at or datetime.now()).isoformat(),
                )
            )

            # Para simplificar la persistencia de las entries, borramos las existentes y reinsertamos.
            # Almacenamiento rápido en SQLite.
            conn.execute("DELETE FROM glossary_entry WHERE glossary_id = ?", (glossary.id,))
            
            for entry in glossary.entries:
                conn.execute(
                    """
                    INSERT INTO glossary_entry
                    (id, glossary_id, source_term, target_term)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        entry.id,
                        glossary.id,
                        entry.source_term,
                        entry.target_term,
                    )
                )

    def get(self, glossary_id: str) -> 'Glossary | None':
        from src.domain.models.glossary import Glossary, GlossaryEntry
        with self.db.transaction() as conn:
            cursor = conn.execute("SELECT * FROM glossary WHERE id = ?", (glossary_id,))
            row = cursor.fetchone()
            if not row:
                return None

            glossary = Glossary(
                id=row["id"],
                project_id=row["project_id"],
                name=row["name"],
                revision=row["revision"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                entries=[]
            )

            entry_cursor = conn.execute("SELECT * FROM glossary_entry WHERE glossary_id = ?", (glossary_id,))
            for erow in entry_cursor.fetchall():
                glossary.entries.append(GlossaryEntry(
                    id=erow["id"],
                    source_term=erow["source_term"],
                    target_term=erow["target_term"]
                ))
            return glossary

    def delete(self, glossary_id: str) -> None:
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM glossary WHERE id = ?", (glossary_id,))
