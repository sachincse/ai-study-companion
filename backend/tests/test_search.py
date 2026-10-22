from app.core.database import get_session_factory
from app.models import User
from app.services.search_service import hybrid_search, keyword_search, query_terms


def test_query_terms_drop_stopwords():
    assert query_terms("What is a page table in paging?") == ["page", "table", "paging"]
    assert query_terms("the the of") == []


def test_keyword_and_hybrid_search_scoped_to_owner(client, auth, other_auth, document):
    factory = get_session_factory()
    with factory() as db:
        owner = db.query(User).filter(User.email == "asha@example.com").one()
        other = db.query(User).filter(User.email == "ravi@example.com").one()

        kw = keyword_search(db, owner.id, "page table frames", top_k=5)
        assert kw, "FTS5 keyword search should find the paging chunk"
        assert "[[" in kw[0][2]  # highlighted snippet

        hits = hybrid_search(db, owner.id, "how does demand paging handle a page fault", top_k=3)
        assert hits and hits[0].document_id == document["id"]
        assert "keyword" in hits[0].methods or "semantic" in hits[0].methods
        assert hits[0].score == 1.0

        assert hybrid_search(db, other.id, "page table", top_k=3) == []
        assert hybrid_search(db, owner.id, "page table", top_k=3, document_ids=[999999]) == []
        assert hybrid_search(db, owner.id, "page table", top_k=3, mode="keyword")
        assert hybrid_search(db, owner.id, "page table", top_k=3, mode="semantic")
