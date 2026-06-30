from datetime import datetime
from flask_login import UserMixin
from app import db


# ─────────────────────────────────────────────────────────────────────────────
# USER
# Stores all three roles: admin, candidate, proctor
# ─────────────────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(120), nullable=False)
    email         = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    # Role controls which blueprint/dashboard the user sees after login
    # Values: 'admin' | 'candidate' | 'proctor'
    role          = db.Column(db.String(20), nullable=False, default="candidate")
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    # An admin user can own many tests
    tests_created = db.relationship("Test", backref="creator", lazy="dynamic",
                                    foreign_keys="Test.created_by")

    # A candidate user can have many attempts (one per test)
    attempts      = db.relationship("Attempt", backref="candidate", lazy="dynamic",
                                    foreign_keys="Attempt.user_id")

    def __repr__(self):
        return f"<User {self.email} [{self.role}]>"

    def is_admin(self):
        return self.role == "admin"

    def is_candidate(self):
        return self.role == "candidate"

    def is_proctor(self):
        return self.role == "proctor"


# ─────────────────────────────────────────────────────────────────────────────
# TEST
# Represents one examination created by an admin
# ─────────────────────────────────────────────────────────────────────────────
class Test(db.Model):
    __tablename__ = "tests"

    id                = db.Column(db.Integer, primary_key=True)
    title             = db.Column(db.String(200), nullable=False)
    description       = db.Column(db.Text, nullable=True)

    # Duration in minutes; enforced on the candidate frontend via countdown timer
    duration_minutes  = db.Column(db.Integer, nullable=False, default=60)

    # Negative marking: 0.0 = disabled, 0.25 = 25% of question marks deducted per wrong answer
    negative_marking  = db.Column(db.Float, nullable=False, default=0.0)

    # Minimum score (float) required to pass this test
    pass_marks        = db.Column(db.Float, nullable=False, default=0.0)

    # Only published tests are visible to candidates
    is_published      = db.Column(db.Boolean, default=False, nullable=False)

    created_by        = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    questions         = db.relationship("Question", backref="test", lazy="dynamic",
                                        cascade="all, delete-orphan",
                                        order_by="Question.order_index")
    attempts          = db.relationship("Attempt", backref="test", lazy="dynamic",
                                        cascade="all, delete-orphan")

    def total_marks(self):
        """Sum of marks across all questions in this test."""
        return sum(q.marks for q in self.questions)

    def question_count(self):
        return self.questions.count()

    def __repr__(self):
        return f"<Test '{self.title}'>"


# ─────────────────────────────────────────────────────────────────────────────
# QUESTION
# One MCQ question belonging to a test
# ─────────────────────────────────────────────────────────────────────────────
class Question(db.Model):
    __tablename__ = "questions"

    id          = db.Column(db.Integer, primary_key=True)
    test_id     = db.Column(db.Integer, db.ForeignKey("tests.id"), nullable=False)
    text        = db.Column(db.Text, nullable=False)

    # Marks awarded for a correct answer
    marks       = db.Column(db.Integer, nullable=False, default=1)

    # Controls display order within the test
    order_index = db.Column(db.Integer, nullable=False, default=0)

    # Relationships
    options     = db.relationship("Option", backref="question", lazy="dynamic",
                                  cascade="all, delete-orphan")
    answers     = db.relationship("Answer", backref="question", lazy="dynamic",
                                  cascade="all, delete-orphan")

    def correct_option(self):
        """Returns the single correct Option for this question."""
        return self.options.filter_by(is_correct=True).first()

    def __repr__(self):
        return f"<Question {self.id}: {self.text[:40]}>"


# ─────────────────────────────────────────────────────────────────────────────
# OPTION
# One answer choice for a question. Exactly one per question has is_correct=True.
# ─────────────────────────────────────────────────────────────────────────────
class Option(db.Model):
    __tablename__ = "options"

    id          = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    text        = db.Column(db.String(500), nullable=False)
    is_correct  = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<Option {self.id} ({'correct' if self.is_correct else 'wrong'})>"


# ─────────────────────────────────────────────────────────────────────────────
# ATTEMPT
# One candidate's session for one test.
# A candidate can only have ONE attempt per test (enforced at route level).
# ─────────────────────────────────────────────────────────────────────────────
class Attempt(db.Model):
    __tablename__ = "attempts"

    id              = db.Column(db.Integer, primary_key=True)
    test_id         = db.Column(db.Integer, db.ForeignKey("tests.id"), nullable=False)
    user_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    started_at      = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at    = db.Column(db.DateTime, nullable=True)

    # Calculated at submission time
    score           = db.Column(db.Float, nullable=True)

    # True once submitted (manually or automatically)
    is_submitted    = db.Column(db.Boolean, default=False, nullable=False)

    # True if the system force-submitted (timer expired or too many violations)
    auto_submitted  = db.Column(db.Boolean, default=False, nullable=False)

    # Relationships
    answers         = db.relationship("Answer", backref="attempt", lazy="dynamic",
                                      cascade="all, delete-orphan")
    suspicious_logs = db.relationship("SuspiciousLog", backref="attempt", lazy="dynamic",
                                      cascade="all, delete-orphan")

    def passed(self):
        """Returns True if the candidate's score meets the pass threshold."""
        if self.score is None:
            return False
        return self.score >= self.test.pass_marks

    def duration_taken(self):
        """Returns time taken in minutes, or None if not submitted."""
        if self.submitted_at and self.started_at:
            delta = self.submitted_at - self.started_at
            return round(delta.total_seconds() / 60, 1)
        return None

    def __repr__(self):
        return f"<Attempt user={self.user_id} test={self.test_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# ANSWER
# Records which option the candidate selected for each question.
# One Answer row per question per attempt.
# ─────────────────────────────────────────────────────────────────────────────
class Answer(db.Model):
    __tablename__ = "answers"

    id                 = db.Column(db.Integer, primary_key=True)
    attempt_id         = db.Column(db.Integer, db.ForeignKey("attempts.id"), nullable=False)
    question_id        = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)

    # Nullable: candidate may skip a question
    selected_option_id = db.Column(db.Integer, db.ForeignKey("options.id"), nullable=True)

    # Set at submission time after comparing selected_option to correct option
    is_correct         = db.Column(db.Boolean, nullable=True)

    # Relationship to the chosen option
    selected_option    = db.relationship("Option", foreign_keys=[selected_option_id])

    def __repr__(self):
        return f"<Answer attempt={self.attempt_id} question={self.question_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# SUSPICIOUS LOG
# Records every anti-cheat violation detected during an attempt.
# Used by proctors to review candidate behavior.
# ─────────────────────────────────────────────────────────────────────────────
class SuspiciousLog(db.Model):
    __tablename__ = "suspicious_logs"

    id           = db.Column(db.Integer, primary_key=True)
    attempt_id   = db.Column(db.Integer, db.ForeignKey("attempts.id"), nullable=False)

    # Event types: tab_switch | fullscreen_exit | copy_attempt | paste_attempt |
    #              right_click | camera_off | screen_share_stopped | auto_submitted
    event_type   = db.Column(db.String(60), nullable=False)

    timestamp    = db.Column(db.DateTime, default=datetime.utcnow)

    # Optional: base64 webcam snapshot captured at the moment of the violation
    snapshot_url = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<SuspiciousLog attempt={self.attempt_id} event={self.event_type}>"