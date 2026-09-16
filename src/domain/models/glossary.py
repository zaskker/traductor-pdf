from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GlossaryEntry:
    id: str
    source_term: str
    target_term: str

    def __post_init__(self):
        if not self.source_term or not self.source_term.strip():
            raise ValueError("source_term cannot be empty")
        if not self.target_term or not self.target_term.strip():
            raise ValueError("target_term cannot be empty")
        self.source_term = self.source_term.strip()
        self.target_term = self.target_term.strip()


@dataclass
class Glossary:
    id: str
    project_id: str
    name: str
    revision: int
    entries: list[GlossaryEntry] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def add_entry(self, entry: GlossaryEntry):
        normalized_source = entry.source_term.lower()
        for e in self.entries:
            if e.source_term.lower() == normalized_source:
                raise ValueError(f"Entry with source term '{entry.source_term}' already exists in glossary.")
        
        self.entries.append(entry)
        self.revision += 1
        
    def remove_entry(self, entry_id: str):
        initial_count = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]
        if len(self.entries) < initial_count:
            self.revision += 1
            
    def update_entry(self, entry_id: str, new_source_term: str, new_target_term: str):
        new_source_term = new_source_term.strip()
        new_target_term = new_target_term.strip()
        
        if not new_source_term:
            raise ValueError("source_term cannot be empty")
        if not new_target_term:
            raise ValueError("target_term cannot be empty")
            
        normalized_new_source = new_source_term.lower()
        
        for e in self.entries:
            if e.id != entry_id and e.source_term.lower() == normalized_new_source:
                raise ValueError(f"Entry with source term '{new_source_term}' already exists in glossary.")

        for e in self.entries:
            if e.id == entry_id:
                has_semantic_changes = e.source_term != new_source_term or e.target_term != new_target_term
                if has_semantic_changes:
                    e.source_term = new_source_term
                    e.target_term = new_target_term
                    self.revision += 1
                return
        
        raise ValueError(f"Entry {entry_id} not found in glossary.")

    def rename(self, new_name: str):
        if not new_name or not new_name.strip():
            raise ValueError("name cannot be empty")
        self.name = new_name.strip()
        # Changing name does not increment revision
