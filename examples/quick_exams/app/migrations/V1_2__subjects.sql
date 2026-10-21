-- Subjects group an instructor's categories, questions and exams. A category
-- belongs to one subject, a question to one subject and one of its
-- categories, and an exam to one subject, whose questions it selects.
--
-- The authoring tables are recreated, so existing categories, questions and
-- exams are removed. Users and archived attempts are kept: archives copy
-- everything they show and have no foreign keys to live content.
--
-- Composite foreign keys keep the hierarchy consistent in the database:
-- (subject_id, owner_id) makes a record's owner its subject's owner,
-- (category_id, subject_id) keeps a question in its category's subject, and
-- exam_questions repeats the exam's subject_id so that an exam can only
-- select questions of its own subject.

DROP TABLE exam_questions;

DROP TABLE questions;

DROP TABLE categories;

DROP TABLE exams;

CREATE TABLE subjects (
	id VARCHAR(32) NOT NULL,
	owner_id VARCHAR(32) NOT NULL,
	name VARCHAR(100) NOT NULL,
	description TEXT NOT NULL DEFAULT '',
	PRIMARY KEY (id),
	UNIQUE (owner_id, name),
	UNIQUE (id, owner_id),
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT
);

CREATE TABLE categories (
	id VARCHAR(32) NOT NULL,
	owner_id VARCHAR(32) NOT NULL,
	subject_id VARCHAR(32) NOT NULL,
	name VARCHAR(100) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (id, subject_id),
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT,
	FOREIGN KEY(subject_id, owner_id) REFERENCES subjects (id, owner_id) ON DELETE RESTRICT
);

CREATE TABLE questions (
	id VARCHAR(32) NOT NULL,
	owner_id VARCHAR(32) NOT NULL,
	subject_id VARCHAR(32) NOT NULL,
	category_id VARCHAR(32) NOT NULL,
	question_text TEXT NOT NULL,
	image TEXT NOT NULL,
	answer_1 TEXT NOT NULL,
	answer_2 TEXT NOT NULL,
	answer_3 TEXT NOT NULL,
	answer_4 TEXT NOT NULL,
	correct_answer INTEGER NOT NULL,
	points FLOAT NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (id, subject_id),
	CHECK (correct_answer BETWEEN 0 AND 3),
	CHECK (points > 0 AND points <= 100000),
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT,
	FOREIGN KEY(subject_id, owner_id) REFERENCES subjects (id, owner_id) ON DELETE RESTRICT,
	FOREIGN KEY(category_id, subject_id) REFERENCES categories (id, subject_id) ON DELETE RESTRICT
);

CREATE TABLE exams (
	id VARCHAR(32) NOT NULL,
	owner_id VARCHAR(32) NOT NULL,
	subject_id VARCHAR(32) NOT NULL,
	title VARCHAR(200) NOT NULL,
	available_from VARCHAR(40) NOT NULL,
	available_until VARCHAR(40) NOT NULL,
	pass_percentage FLOAT NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (id, subject_id),
	CHECK (pass_percentage BETWEEN 0 AND 100),
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT,
	FOREIGN KEY(subject_id, owner_id) REFERENCES subjects (id, owner_id) ON DELETE RESTRICT
);

CREATE TABLE exam_questions (
	id VARCHAR(32) NOT NULL,
	exam_id VARCHAR(32) NOT NULL,
	subject_id VARCHAR(32) NOT NULL,
	question_id VARCHAR(32) NOT NULL,
	position INTEGER NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (exam_id, question_id),
	UNIQUE (exam_id, position),
	CHECK (position >= 0),
	FOREIGN KEY(exam_id, subject_id) REFERENCES exams (id, subject_id) ON DELETE CASCADE,
	FOREIGN KEY(question_id, subject_id) REFERENCES questions (id, subject_id) ON DELETE RESTRICT
);

CREATE INDEX ix_subjects_owner_id ON subjects (owner_id);
CREATE INDEX ix_categories_owner_id ON categories (owner_id);
CREATE INDEX ix_categories_subject_id ON categories (subject_id, owner_id);
CREATE INDEX ix_questions_owner_id ON questions (owner_id);
CREATE INDEX ix_questions_subject_id ON questions (subject_id, owner_id);
CREATE INDEX ix_questions_category_id ON questions (category_id, subject_id);
CREATE INDEX ix_exams_owner_id ON exams (owner_id);
CREATE INDEX ix_exams_subject_id ON exams (subject_id, owner_id);
CREATE INDEX ix_exam_questions_exam_id ON exam_questions (exam_id, subject_id);
CREATE INDEX ix_exam_questions_question_id ON exam_questions (question_id, subject_id);
