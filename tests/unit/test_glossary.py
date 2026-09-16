import pytest
from src.domain.models.glossary import Glossary, GlossaryEntry

def test_glossary_revision_ownership():
    glossary = Glossary(id="g1", project_id="p1", name="Test Glossary", revision=1)
    
    # 1. Increment on adding entry
    entry1 = GlossaryEntry(id="e1", source_term="apple", target_term="manzana")
    glossary.add_entry(entry1)
    assert glossary.revision == 2
    
    # 2. Increment on updating entry (source or target)
    glossary.update_entry("e1", "apple", "manzana verde")
    assert glossary.revision == 3
    
    # 3. Increment on removing entry
    glossary.remove_entry("e1")
    assert glossary.revision == 4
    
    # 4. Modifying just the name MUST NOT increment the revision
    glossary.rename("My Super Glossary")
    assert glossary.revision == 4
    assert glossary.name == "My Super Glossary"
