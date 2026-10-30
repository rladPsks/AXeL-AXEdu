from backend.db import Database
from backend.seed import seed
from backend.seed_support import seed_support


def test_support_staff_are_idempotent_and_preserve_account_changes(tmp_path):
    path = tmp_path / "support.sqlite3"
    seed(path)
    seed_support(path)
    database = Database(path)
    with database.transaction() as db:
        assert db.execute("SELECT user_id FROM school_responsibilities WHERE id='resp-life'").fetchone()[0] == "life-head"
        assert db.execute("SELECT label FROM school_responsibilities WHERE id='resp-life'").fetchone()[0] == "생활부장"
        assert db.execute("SELECT user_id FROM school_responsibilities WHERE id='resp-academic'").fetchone()[0] == "academic-head"
        count = db.execute("SELECT COUNT(*) FROM memberships").fetchone()[0]
        db.execute("UPDATE memberships SET active=0 WHERE user_id='work-support'")
    seed_support(path)
    with database.transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM memberships").fetchone()[0] == count
        assert db.execute("SELECT active FROM memberships WHERE user_id='work-support'").fetchone()[0] == 0


def test_support_staff_do_not_seed_unmarked_databases(tmp_path):
    path = tmp_path / "ordinary.sqlite3"
    seed_support(path)
    with Database(path).transaction() as db:
        assert db.execute("SELECT COUNT(*) FROM memberships").fetchone()[0] == 0
