from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Text, DateTime, Float, func
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    group_name = Column(String(50), nullable=True)
    user_type = Column(String(20), nullable=False)  # 'student', 'helper', 'teacher'
    rating = Column(Float, default=0.0)
    completed_tasks = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    tasks_created = relationship('Task', back_populates='student', foreign_keys='Task.student_id')
    tasks_helped = relationship('Task', back_populates='helper', foreign_keys='Task.helper_id')

class Subject(Base):
    __tablename__ = 'subjects'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(20), default='new')  # 'new', 'in_progress', 'completed'
    created_at = Column(DateTime, default=datetime.now)
    deadline    = Column(DateTime, nullable=False)
    photo_id = Column(String(200), nullable=True)
    solution_text = Column(Text, nullable=True)
    solution_file_id = Column(String(200), nullable=True)
    rating = Column(Integer, nullable=True)
    teacher_name = Column(String(100), nullable=False)

    # Foreign keys
    student_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    helper_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=False)

    # Relationships
    student = relationship('User', back_populates='tasks_created', foreign_keys=[student_id])
    helper = relationship('User', back_populates='tasks_helped', foreign_keys=[helper_id])
    subject = relationship('Subject')

# Database initialization
engine = create_engine('sqlite:///student_helper.db')
Session = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)
    print("Database initialized successfully!")

if __name__ == "__main__":
    init_db()