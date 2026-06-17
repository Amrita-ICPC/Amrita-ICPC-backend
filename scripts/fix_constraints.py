import asyncio

from sqlalchemy import text

from app.core.clients.database import engine


async def main():
    print("Connecting to database...")
    async with engine.begin() as conn:
        print("Updating foreign key constraints to ON DELETE CASCADE...")

        statements = [
            # 1. submission_testcase -> testcase
            """
            ALTER TABLE submission_testcase DROP CONSTRAINT IF EXISTS submission_testcase_testcase_id_fkey;
            """,
            """
            ALTER TABLE submission_testcase ADD CONSTRAINT submission_testcase_testcase_id_fkey
                FOREIGN KEY (testcase_id) REFERENCES testcase(id) ON DELETE CASCADE;
            """,
            # 2. submission_testcase -> submission
            """
            ALTER TABLE submission_testcase DROP CONSTRAINT IF EXISTS submission_testcase_submission_id_fkey;
            """,
            """
            ALTER TABLE submission_testcase ADD CONSTRAINT submission_testcase_submission_id_fkey
                FOREIGN KEY (submission_id) REFERENCES submission(id) ON DELETE CASCADE;
            """,
            # 3. contest_submission -> submission
            """
            ALTER TABLE contest_submission DROP CONSTRAINT IF EXISTS contest_submission_submission_id_fkey;
            """,
            """
            ALTER TABLE contest_submission ADD CONSTRAINT contest_submission_submission_id_fkey
                FOREIGN KEY (submission_id) REFERENCES submission(id) ON DELETE CASCADE;
            """,
            # 4. submission -> question
            """
            ALTER TABLE submission DROP CONSTRAINT IF EXISTS submission_question_id_fkey;
            """,
            """
            ALTER TABLE submission ADD CONSTRAINT submission_question_id_fkey
                FOREIGN KEY (question_id) REFERENCES question(id) ON DELETE CASCADE;
            """,
            # 5. testcase -> question
            """
            ALTER TABLE testcase DROP CONSTRAINT IF EXISTS testcase_question_id_fkey;
            """,
            """
            ALTER TABLE testcase ADD CONSTRAINT testcase_question_id_fkey
                FOREIGN KEY (question_id) REFERENCES question(id) ON DELETE CASCADE;
            """,
            # 6. question_template -> question
            """
            ALTER TABLE question_template DROP CONSTRAINT IF EXISTS question_template_question_id_fkey;
            """,
            """
            ALTER TABLE question_template ADD CONSTRAINT question_template_question_id_fkey
                FOREIGN KEY (question_id) REFERENCES question(id) ON DELETE CASCADE;
            """,
            # 7. question_language -> question
            """
            ALTER TABLE question_language DROP CONSTRAINT IF EXISTS question_language_question_id_fkey;
            """,
            """
            ALTER TABLE question_language ADD CONSTRAINT question_language_question_id_fkey
                FOREIGN KEY (question_id) REFERENCES question(id) ON DELETE CASCADE;
            """,
        ]

        for stmt in statements:
            await conn.execute(text(stmt))

        print("Successfully updated all foreign key constraints to ON DELETE CASCADE!")


if __name__ == "__main__":
    asyncio.run(main())
