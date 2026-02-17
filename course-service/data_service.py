# course-service/data_service.py
from models import Course

class CourseMockDataService:
    def __init__(self):
        self.courses = [
            Course(id=1, name="Introduction to Computer Science", code="CS101", credits=3, instructor="Dr. Smith", description="Basic concepts of computer science"),
            Course(id=2, name="Data Structures and Algorithms", code="CS201", credits=4, instructor="Dr. Johnson", description="Advanced data structures and algorithm design"),
            Course(id=3, name="Database Systems", code="CS301", credits=3, instructor="Dr. Williams", description="Relational database design and SQL"),
        ]
        self.next_id = 4

    def get_all_courses(self):
        return self.courses

    def get_course_by_id(self, course_id: int):
        return next((c for c in self.courses if c.id == course_id), None)

    def add_course(self, course_data):
        new_course = Course(id=self.next_id, **course_data.model_dump())
        self.courses.append(new_course)
        self.next_id += 1
        return new_course

    def update_course(self, course_id: int, course_data):
        course = self.get_course_by_id(course_id)
        if course:
            update_data = course_data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(course, key, value)
            return course
        return None

    def delete_course(self, course_id: int):
        course = self.get_course_by_id(course_id)
        if course:
            self.courses.remove(course)
            return True
        return False
