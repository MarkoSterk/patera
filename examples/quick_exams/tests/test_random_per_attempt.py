from patera.testing import PateraTestClient
from test_quick_exams import Api, login, question_body, subject, window


async def setup_bank(teacher):
    """A subject with a 6-question category, a 2-question category and an empty one."""
    biology = await subject(teacher, "Biology")
    names = ("Muscles", "Joints", "Empty")
    cats = [
        await teacher(
            "POST",
            "/api/categories/",
            201,
            json={"subject_id": biology["id"], "name": name},
        )
        for name in names
    ]
    muscles = [
        await teacher(
            "POST",
            "/api/questions/",
            201,
            json=question_body(cats[0], question_text=f"Muscle {n}?"),
        )
        for n in range(6)
    ]
    joints = [
        await teacher(
            "POST",
            "/api/questions/",
            201,
            json=question_body(cats[1], question_text=f"Joint {n}?"),
        )
        for n in range(2)
    ]
    return biology, cats, muscles, joints


def per_attempt(subject_id, category_ids, count, **changes):
    return {
        "subject_id": subject_id,
        "title": "Random for everyone",
        **window(),
        "random": {"category_ids": category_ids, "count": count, "per_attempt": True},
        **changes,
    }


async def start(client, exam_id, email="student@example.com"):
    return await client.post(
        "/api/attempts/", json={"exam_id": exam_id, "email": email}
    )


async def test_every_attempt_draws_its_own_questions(exams_app, db):
    async with PateraTestClient(exams_app) as client:
        teacher = Api(client, await login(client))
        biology, (muscles_cat, joints_cat, _), muscles, joints = await setup_bank(
            teacher
        )

        # The pool must hold at least as many questions as each attempt draws.
        await teacher(
            "POST",
            "/api/exams/",
            400,
            json=per_attempt(biology["id"], [joints_cat["id"]], 3),
        )
        exam = await teacher(
            "POST",
            "/api/exams/",
            201,
            json=per_attempt(biology["id"], [muscles_cat["id"], joints_cat["id"]], 3),
        )
        assert exam["random_per_attempt"] is True
        assert exam["random_count"] == 3
        assert sorted(exam["category_ids"]) == sorted(
            [muscles_cat["id"], joints_cat["id"]]
        )
        assert exam["question_ids"] == []
        assert db.execute("SELECT COUNT(*) FROM exam_questions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM exam_categories").fetchone()[0] == 2
        assert await teacher("GET", "/api/exams/") == [exam]

        pool = {q["id"] for q in muscles + joints}
        drawn = []
        for n in range(12):
            response = await start(client, exam["id"], f"student{n}@example.com")
            assert response.status_code == 201, response.text
            ids = [q["id"] for q in response.json()["questions"]]
            assert len(ids) == len(set(ids)) == 3 and set(ids) <= pool
            drawn.append(frozenset(ids))
        # 12 identical draws out of C(8, 3) = 56 sets would be (1/56)^11.
        assert len(set(drawn)) > 1

        # Each attempt is graded on the questions it received.
        response = await start(client, exam["id"])
        attempt = response.json()
        answers = {q["id"]: 1 for q in attempt["questions"]}
        result = (
            await client.post(
                f"/api/attempts/{attempt['id']}/submit", json={"answers": answers}
            )
        ).json()
        assert result["percentage"] == 100 and result["passed"] is True
        report = (await teacher("GET", "/api/reports/"))[0]
        assert report["count"] == 1
        assert len(report["attempts"][0]["questions"]) == 3

        # The categories of a per-attempt exam cannot disappear or move.
        await teacher("DELETE", f"/api/categories/{joints_cat['id']}", 409)
        other_subject = await subject(teacher, "Chemistry")
        await teacher(
            "PUT",
            f"/api/categories/{muscles_cat['id']}",
            409,
            json={"subject_id": other_subject["id"], "name": "Muscles"},
        )

        # When questions are removed below the count, starting fails clearly.
        for question in muscles:
            await teacher("DELETE", f"/api/questions/{question['id']}", 204)
        response = await start(client, exam["id"])
        assert response.status_code == 400
        assert "not have enough questions" in response.text


async def test_switching_modes_and_deleting(exams_app, db):
    async with PateraTestClient(exams_app) as client:
        teacher = Api(client, await login(client))
        biology, (muscles_cat, joints_cat, _), muscles, _ = await setup_bank(teacher)
        exam = await teacher(
            "POST",
            "/api/exams/",
            201,
            json=per_attempt(biology["id"], [muscles_cat["id"]], 2),
        )

        # A fixed selection replaces the category pool ...
        fixed = await teacher(
            "PUT",
            f"/api/exams/{exam['id']}",
            json={
                "subject_id": biology["id"],
                "title": "Fixed",
                **window(),
                "question_ids": [muscles[0]["id"]],
            },
        )
        assert fixed["random_per_attempt"] is False
        assert fixed["random_count"] is None and fixed["category_ids"] == []
        assert db.execute("SELECT COUNT(*) FROM exam_categories").fetchone()[0] == 0
        response = await start(client, exam["id"])
        assert [q["id"] for q in response.json()["questions"]] == [muscles[0]["id"]]

        # ... a one-time random draw stores questions, not categories ...
        once = await teacher(
            "PUT",
            f"/api/exams/{exam['id']}",
            json={
                "subject_id": biology["id"],
                "title": "Once",
                **window(),
                "random": {"category_ids": [muscles_cat["id"]], "count": 2},
            },
        )
        assert once["random_per_attempt"] is False and len(once["question_ids"]) == 2
        assert once["category_ids"] == []

        # ... and back again; deleting the exam removes its pool.
        await teacher(
            "PUT",
            f"/api/exams/{exam['id']}",
            json=per_attempt(biology["id"], [muscles_cat["id"]], 2),
        )
        assert db.execute("SELECT COUNT(*) FROM exam_questions").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM exam_categories").fetchone()[0] == 1
        await teacher("DELETE", f"/api/exams/{exam['id']}", 204)
        assert db.execute("SELECT COUNT(*) FROM exam_categories").fetchone()[0] == 0
        await teacher(
            "DELETE", f"/api/categories/{joints_cat['id']}", 409
        )  # still has questions


async def test_per_attempt_pool_must_belong_to_the_exam_subject(exams_app):
    async with PateraTestClient(exams_app) as client:
        teacher = Api(client, await login(client))
        biology, (muscles_cat, *_), _, _ = await setup_bank(teacher)
        chemistry = await subject(teacher, "Chemistry")
        await teacher(
            "POST",
            "/api/exams/",
            400,
            json=per_attempt(chemistry["id"], [muscles_cat["id"]], 1),
        )
        await teacher(
            "POST", "/api/exams/", 422, json=per_attempt(biology["id"], [], 1)
        )
