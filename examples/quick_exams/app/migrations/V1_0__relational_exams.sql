-- Quick Exams relational schema. Applied through patera migrate.


CREATE TABLE users (
	email VARCHAR(254) NOT NULL,
	password_hash TEXT NOT NULL,
	is_instructor BOOLEAN NOT NULL,
	is_admin BOOLEAN NOT NULL,
	id VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (email)
)

;


CREATE TABLE attempts (
	owner_id VARCHAR(32) NOT NULL,
	source_exam_id VARCHAR(32) NOT NULL,
	student_email VARCHAR(254) NOT NULL,
	started_at VARCHAR(40) NOT NULL,
	submitted_at VARCHAR(40),
	exam_title VARCHAR(200) NOT NULL,
	available_from VARCHAR(40) NOT NULL,
	available_until VARCHAR(40) NOT NULL,
	pass_percentage FLOAT NOT NULL,
	earned_points FLOAT,
	maximum_points FLOAT,
	score_percentage FLOAT,
	passed BOOLEAN,
	id VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT
)

;


CREATE TABLE categories (
	owner_id VARCHAR(32) NOT NULL,
	name VARCHAR(100) NOT NULL,
	id VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT
)

;


CREATE TABLE exams (
	owner_id VARCHAR(32) NOT NULL,
	title VARCHAR(200) NOT NULL,
	available_from VARCHAR(40) NOT NULL,
	available_until VARCHAR(40) NOT NULL,
	pass_percentage FLOAT NOT NULL,
	id VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	CHECK (pass_percentage BETWEEN 0 AND 100),
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT
)

;


CREATE TABLE sessions (
	user_id VARCHAR(32) NOT NULL,
	created_at VARCHAR(40) NOT NULL,
	id VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

;


CREATE TABLE attempt_questions (
	attempt_id VARCHAR(32) NOT NULL,
	position INTEGER NOT NULL,
	source_question_id VARCHAR(32) NOT NULL,
	source_category_id VARCHAR(32) NOT NULL,
	question_text TEXT NOT NULL,
	image TEXT NOT NULL,
	answer_1 TEXT NOT NULL,
	answer_2 TEXT NOT NULL,
	answer_3 TEXT NOT NULL,
	answer_4 TEXT NOT NULL,
	correct_answer INTEGER NOT NULL,
	points FLOAT NOT NULL,
	selected_answer INTEGER,
	id VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (attempt_id, position),
	UNIQUE (attempt_id, source_question_id),
	CHECK (correct_answer BETWEEN 0 AND 3),
	CHECK (selected_answer IS NULL OR selected_answer BETWEEN 0 AND 3),
	CHECK (points > 0),
	FOREIGN KEY(attempt_id) REFERENCES attempts (id) ON DELETE RESTRICT
)

;


CREATE TABLE questions (
	owner_id VARCHAR(32) NOT NULL,
	category_id VARCHAR(32) NOT NULL,
	question_text TEXT NOT NULL,
	image TEXT NOT NULL,
	answer_1 TEXT NOT NULL,
	answer_2 TEXT NOT NULL,
	answer_3 TEXT NOT NULL,
	answer_4 TEXT NOT NULL,
	correct_answer INTEGER NOT NULL,
	points FLOAT NOT NULL,
	id VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	CHECK (correct_answer BETWEEN 0 AND 3),
	CHECK (points > 0 AND points <= 100000),
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE RESTRICT,
	FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE RESTRICT
)

;


CREATE TABLE exam_questions (
	exam_id VARCHAR(32) NOT NULL,
	question_id VARCHAR(32) NOT NULL,
	position INTEGER NOT NULL,
	id VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (exam_id, question_id),
	UNIQUE (exam_id, position),
	CHECK (position >= 0),
	FOREIGN KEY(exam_id) REFERENCES exams (id) ON DELETE CASCADE,
	FOREIGN KEY(question_id) REFERENCES questions (id) ON DELETE RESTRICT
)

;

CREATE INDEX ix_attempts_owner_id ON attempts (owner_id);
CREATE INDEX ix_attempts_source_exam_id ON attempts (source_exam_id);
CREATE INDEX ix_categories_owner_id ON categories (owner_id);
CREATE INDEX ix_exams_owner_id ON exams (owner_id);
CREATE INDEX ix_sessions_user_id ON sessions (user_id);
CREATE INDEX ix_attempt_questions_attempt_id ON attempt_questions (attempt_id);
CREATE INDEX ix_questions_category_id ON questions (category_id);
CREATE INDEX ix_questions_owner_id ON questions (owner_id);
CREATE INDEX ix_exam_questions_exam_id ON exam_questions (exam_id);
CREATE INDEX ix_exam_questions_question_id ON exam_questions (question_id);
