-- Exams that draw a different random set of questions for every attempt.
--
-- Such an exam stores no fixed question selection. It keeps the categories
-- it draws from in exam_categories and the number of questions per attempt
-- in exams.random_count; when a student starts, that many questions are
-- sampled from the categories' current questions and copied into the
-- attempt, as for any other exam. Existing exams keep their fixed selection.
--
-- exam_categories repeats the exam's subject_id, so an exam can only draw
-- from categories of its own subject, like exam_questions.

ALTER TABLE exams ADD COLUMN random_per_attempt BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE exams ADD COLUMN random_count INTEGER CHECK (random_count IS NULL OR random_count >= 1);

CREATE TABLE exam_categories (
	id VARCHAR(32) NOT NULL,
	exam_id VARCHAR(32) NOT NULL,
	subject_id VARCHAR(32) NOT NULL,
	category_id VARCHAR(32) NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (exam_id, category_id),
	FOREIGN KEY(exam_id, subject_id) REFERENCES exams (id, subject_id) ON DELETE CASCADE,
	FOREIGN KEY(category_id, subject_id) REFERENCES categories (id, subject_id) ON DELETE RESTRICT
);

CREATE INDEX ix_exam_categories_exam_id ON exam_categories (exam_id, subject_id);
CREATE INDEX ix_exam_categories_category_id ON exam_categories (category_id, subject_id);
