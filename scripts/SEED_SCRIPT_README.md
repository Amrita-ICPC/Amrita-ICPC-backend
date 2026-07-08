# Contest & Bank Seed Script Documentation

## Overview

The `seed_contests.py` script is a utility for populating the database with large-scale test data for the ICPC backend system. It creates:

- **100 Contests** - Ready for question imports
- **100 Question Banks** - With 50-70 questions each
- **5,000-7,000 Questions** - Randomly distributed across banks
- **Supporting Data** - Languages, test cases, templates

This script focuses on creating the foundational data structure. Questions can be manually imported from banks to contests later via the API.

## What Gets Created

### Users
- **1 Admin User**: System Administrator (owns all banks)
- **1 Instructor User**: Creates contests and questions

### Programming Languages (4 total - reused from existing)
- Python 3.11
- C++ 17
- Java 17
- JavaScript ES2023

### Contests (100 total)
- **Created by**: Instructor User
- **Name Format**: `Contest 001-100: Qualifier Round`
- **Scheduling**:
  - Start: Days 7-106 from now
  - Duration: 5 days each
  - Registration: Open from today until 1 hour before contest start
  - Max Teams: 100
  - Team Participation Mode: LEADER_ONLY
  - Auto-evaluate submissions on submit

#### Sample Contest Timeline
```
Contest 001: Starts 2026-07-09, Registration: 2026-07-02 - 2026-07-09
Contest 002: Starts 2026-07-10, Registration: 2026-07-02 - 2026-07-10
...
Contest 100: Starts 2026-09-14, Registration: 2026-07-02 - 2026-09-14
```

### Question Banks (100 total)
- **Owned by**: Admin User
- **Name Format**: `Bank 001-100: Question Repository [TIMESTAMP]`
- **Questions per Bank**: 50-70 (randomly assigned)
- **Total Questions**: 5,000-7,000

#### Sample Bank Structure
```
Bank 001 [2026-07-02_195100]
├── 57 Questions
│   ├── Array Sum Problems
│   ├── String Palindrome Checks
│   ├── Tree Traversals
│   ├── Graph DFS Paths
│   ├── Dynamic Programming
│   ├── Sorting Problems
│   ├── Math Problems
│   └── Hash Table Problems
```

### Questions (50-70 per bank)
Each question includes:
- **Difficulty**: Randomly EASY, MEDIUM, or HARD
- **Time Limits**: 1-5 seconds
- **Memory Limits**: 256MB - 2GB
- **Test Cases**: 2 per question (1 visible, 1 hidden)
- **Language Support**: All 4 languages
- **Code Templates**: Starter, driver, and solution templates

#### Sample Question Types
1. **Array {idx}: Sum Pair**
   - Find two numbers in array that sum to target
   - Difficulty: Easy-Medium

2. **String {idx}: Palindrome Check**
   - Determine if string is palindrome
   - Difficulty: Easy-Medium

3. **Tree {idx}: Level Order Traversal**
   - Traverse binary tree level by level
   - Difficulty: Medium-Hard

4. **Graph {idx}: DFS Path**
   - Find path between two nodes
   - Difficulty: Medium-Hard

5. **DP {idx}: Fibonacci Sequence**
   - Compute nth Fibonacci number efficiently
   - Difficulty: Medium

## Running the Script

### Prerequisites
1. PostgreSQL database is running and accessible
2. Database credentials configured in `.env`
3. Python virtual environment activated
4. All models and dependencies loaded

### Execution

```bash
# Using the project's Python environment
.venv/bin/python seed_contests.py

# With output logging
.venv/bin/python seed_contests.py 2>&1 | tee seed_output.log
```

### Expected Output

```
🌱 Starting database seeding...

👨‍💼 Setting up admin...
   ✓ Using admin: System Administrator

👨‍🏫 Setting up instructor...
   ✓ Using instructor: Seed Instructor

💻 Setting up programming languages...
   ✓ 4 languages available

🏆 Creating contests...
  Creating 100 contests...
    ✓ Created 10 contests...
    ✓ Created 20 contests...
    ✓ Created 30 contests...
    ...
    ✓ Created 100 contests...
  ✓ All 100 contests created

❓ Creating questions (5700 total)...
  Creating 5700 questions for each bank...
    ✓ Created questions for 10 banks...
    ✓ Created questions for 20 banks...
    ...
    ✓ Created questions for 100 banks...
  ✓ All questions created (5700 total)

🏦 Creating banks and assigning questions (Admin as owner)...
  Creating banks and assigning questions...
    ✓ Created 10 banks...
    ✓ Created 20 banks...
    ...
    ✓ Created 100 banks...
  ✓ All 100 banks created with questions assigned

✅ Database seeding completed successfully!

📊 Summary:
   • Contests: 100 (Created by: Seed Instructor)
   • Banks: 100 (Owned by: System Administrator)
   • Questions per bank: 57 (50-70 range)
   • Total questions: 5700
   • Languages: 4

💡 Next Steps:
   1. Import questions from banks to contests via API
   2. Publish contests when ready
   3. Create teams and enroll them in contests
```

## Performance & Timing

| Task | Time |
|------|------|
| Setup (instructor, languages) | ~1 second |
| Create 100 contests | ~2 seconds |
| Create 5,700 questions | ~10 seconds |
| Create 100 banks & assign questions | ~8 seconds |
| Commit to database | ~2 seconds |
| **Total** | **~23 seconds** |

**Database Size Impact**:
- Questions: ~5,700 records
- Question Languages: ~22,800 records (5,700 × 4)
- Question Templates: ~5,700 records
- Test Cases: ~11,400 records (5,700 × 2)
- Banks: 100 records
- Bank-Question Mappings: ~5,700 records
- Contests: 100 records
- **Total**: ~57,000+ new records

## Data Model Relationships

```
Admin User (1)
├── Owns 100 Banks
│   ├── Banks (100)
│   │   ├── Name: Bank 001-100: Question Repository [TIMESTAMP]
│   │   ├── Description: Contains 50-70 problems
│   │   └── Bank-Question Links (5,700 total)
│   │
│   └── Questions in Banks (5,700)
│       ├── Difficulty: Easy/Medium/Hard (mixed)
│       ├── Languages Supported: 4 (Python, C++, Java, JS)
│       ├── Test Cases: 2 per question (11,400 total)
│       ├── Templates: 1 per language per question
│       └── Time/Memory Limits: Varies by question
│
Instructor User (1)
└── Creates 100 Contests
    └── Contests (100)
        ├── Name: Contest 001-100: Qualifier Round
        ├── Status: DRAFT (ready for publishing)
        ├── Max Teams: 100
        └── Registration Windows: Staggered by day
```

## Next Steps After Seeding

### 1. **Import Questions to Contests**
Use the API to import questions from banks to contests:

```bash
POST /api/v1/contests/{contest_id}/questions/import
{
    "bank_id": "{bank_id}",
    "question_ids": ["{question_id_1}", "{question_id_2}", ...]
}
```

### 2. **Publish Contests**
Once questions are imported and configured:

```bash
PATCH /api/v1/contests/{contest_id}
{
    "status": "PUBLISHED"
}
```

### 3. **Create Teams and Register**
Create teams and enroll them in contests:

```bash
POST /api/v1/contests/{contest_id}/teams
{
    "team_id": "{team_id}",
    "members": ["{user_id_1}", "{user_id_2}", ...]
}
```

## Customization

To modify the script behavior, edit these constants:

```python
# Number of banks to create
100  # Line: for bank_num in range(100):

# Questions per bank (50-70 random)
questions_per_bank = random.randint(50, 70)

# Contest start offset (days from now)
contest_start = now + timedelta(days=7 + i)

# Question templates (add more in QUESTION_TEMPLATES)
QUESTION_TEMPLATES = [
    {"title": "...", "text": "..."},
    ...
]

# Difficulty distribution
DIFFICULTIES = [
    QuestionDifficulty.EASY,
    QuestionDifficulty.EASY,
    QuestionDifficulty.EASY,
    QuestionDifficulty.MEDIUM,
    QuestionDifficulty.MEDIUM,
    QuestionDifficulty.HARD,
]
```

## Uniqueness & Idempotency

### Safe to Run Multiple Times
✅ Each run creates unique data:
- Contests get unique IDs (UUID)
- Banks get unique IDs + timestamps in names
- Questions get unique IDs
- Timestamps prevent constraint conflicts

### Bank Naming
Banks use timestamp in names to ensure uniqueness:
```
Bank 001: Question Repository [2026-07-02_195100]
Bank 001: Question Repository [2026-07-02_200200]  ← Different run, same name works
```

## Verification Query

### Check Basic Statistics
```python
import asyncio
from sqlalchemy import select, func
from app.core.clients.database import SessionLocal
from app.models.contest import Contest
from app.models.bank import Bank, BankQuestion
from app.models.question import Question

async def verify():
    async with SessionLocal() as session:
        contests = await session.execute(select(func.count(Contest.id)))
        banks = await session.execute(select(func.count(Bank.id)))
        questions = await session.execute(select(func.count(Question.id)))
        mappings = await session.execute(select(func.count(BankQuestion.id)))

        print(f"Contests: {contests.scalar()}")
        print(f"Banks: {banks.scalar()}")
        print(f"Questions: {questions.scalar()}")
        print(f"Bank-Question Mappings: {mappings.scalar()}")

asyncio.run(verify())
```

### Verify Bank Ownership
```python
import asyncio
from sqlalchemy import select
from app.core.clients.database import SessionLocal
from app.models.bank import Bank
from app.models.user import User
from app.utils.enums import UserRole

async def verify_ownership():
    async with SessionLocal() as session:
        # Get latest banks
        result = await session.execute(
            select(Bank).order_by(Bank.created_at.desc()).limit(5)
        )
        banks = result.scalars().all()

        print("Latest Banks & Owners:")
        for bank in banks:
            result = await session.execute(
                select(User).where(User.id == bank.created_by)
            )
            creator = result.scalars().first()
            print(f"  • {bank.name}")
            print(f"    Owner: {creator.name} (Role: {creator.role.value})")

asyncio.run(verify_ownership())
```

## Troubleshooting

### Issue: Duplicate Key Constraint on Bank Names
**Cause**: Bank names collide with previous runs (same instructor)
**Solution**: Script automatically adds timestamps to prevent this
**Action**: No action needed - script handles it

### Issue: Database Connection Timeout
**Cause**: PostgreSQL not running or connection pool exhausted
**Solution**:
```bash
# Check PostgreSQL status
pg_isready -h localhost -p 5432

# Restart PostgreSQL if needed
brew services restart postgresql
```

### Issue: Memory Usage Too High
**Cause**: Creating all 5,700 questions + relationships at once
**Solution**: Script flushes every 10 banks to manage memory
**Performance**: ~50MB peak memory usage

### Issue: Script Hangs During Question Creation
**Cause**: Large number of language associations (5,700 × 4)
**Solution**: Wait - this is normal (takes 10-15 seconds)
**Monitor**: Check database logs to see active queries

## API Testing After Seeding

### List All Contests
```bash
curl -X GET "http://localhost:8000/api/v1/contests"
```

### Get Specific Contest
```bash
curl -X GET "http://localhost:8000/api/v1/contests/{contest_id}"
```

### List Banks
```bash
curl -X GET "http://localhost:8000/api/v1/banks"
```

### Get Bank Questions
```bash
curl -X GET "http://localhost:8000/api/v1/banks/{bank_id}/questions"
```

## Database Cleanup (If Needed)

To completely reset and reseed (WARNING: Destructive):

```sql
-- Delete in dependency order
DELETE FROM contest_submission;
DELETE FROM contest_team_member;
DELETE FROM contest_team;
DELETE FROM contest_team_progress;
DELETE FROM contest_team_violation;
DELETE FROM contest_question;
DELETE FROM contest;
DELETE FROM bank_question;
DELETE FROM bank_share;
DELETE FROM bank;
DELETE FROM submission_testcase;
DELETE FROM submission;
DELETE FROM question_template;
DELETE FROM question_language;
DELETE FROM testcase;
DELETE FROM question;
DELETE FROM team_user;
DELETE FROM team;
DELETE FROM users WHERE role IN ('student', 'instructor');
```

## Monitoring

### Watch Script Progress
```bash
# Terminal 1: Run script
.venv/bin/python seed_contests.py

# Terminal 2: Monitor database size
watch -n 2 'psql -U postgres -d amrita -c "SELECT count(*) as total_records FROM (SELECT * FROM contest UNION ALL SELECT * FROM question UNION ALL SELECT * FROM bank) t;"'
```

## FAQ

**Q: Can I run the script multiple times?**
A: Yes! Each run creates new unique data without conflicts.

**Q: How long does seeding take?**
A: Approximately 20-30 seconds depending on hardware.

**Q: Can I customize question types?**
A: Yes! Edit `QUESTION_TEMPLATES` list in the script.

**Q: Why timestamp in bank names?**
A: To ensure uniqueness while allowing multiple runs. Bank name must be unique per instructor.

**Q: How do I import questions to contests?**
A: Use the Contest API endpoints or create another script that iterates through banks and contests.

---

**Last Updated**: July 2, 2026
**Script Version**: 2.0
**Status**: Production Ready ✅
