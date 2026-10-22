from sqlalchemy import create_engine, text

from app.database import migrate_activity_delete_action


def test_migration_adds_deleted_activity_action_without_losing_history(tmp_path):
    old_engine = create_engine(f"sqlite:///{tmp_path / 'pre_delete.db'}")
    try:
        with old_engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TABLE activities (
                    id VARCHAR(36) PRIMARY KEY,
                    action VARCHAR(20) NOT NULL CHECK (action IN ('created', 'moved')),
                    card_id VARCHAR(36) NOT NULL,
                    card_title VARCHAR(200) NOT NULL,
                    from_column VARCHAR(32),
                    to_column VARCHAR(32) NOT NULL,
                    message TEXT NOT NULL,
                    created_at DATETIME NOT NULL
                )
            """)
            connection.exec_driver_sql(
                "CREATE INDEX ix_activities_created_at ON activities (created_at)"
            )
            connection.execute(text("""
                INSERT INTO activities
                  (id, action, card_id, card_title, from_column, to_column, message, created_at)
                VALUES ('old-event', 'created', 'card-1', 'Old task', NULL, 'todo',
                        'Created old task', '2026-01-01T00:00:00')
            """))

        assert migrate_activity_delete_action(old_engine) is True
        assert migrate_activity_delete_action(old_engine) is False  # idempotent

        with old_engine.begin() as connection:
            old_row = connection.execute(text(
                "SELECT action, card_title FROM activities WHERE id='old-event'"
            )).one()
            assert tuple(old_row) == ('created', 'Old task')
            connection.execute(text("""
                INSERT INTO activities
                  (id, action, card_id, card_title, from_column, to_column, message, created_at)
                VALUES ('delete-event', 'deleted', 'card-2', 'Removed task', 'doing', 'doing',
                        'Deleted Removed task from In Progress', '2026-01-02T00:00:00')
            """))
            assert connection.execute(text(
                "SELECT action FROM activities WHERE id='delete-event'"
            )).scalar_one() == 'deleted'
    finally:
        old_engine.dispose()
