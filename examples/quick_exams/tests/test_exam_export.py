import base64
import struct
import zlib
from io import BytesIO

from docx import Document
from patera.testing import PateraTestClient
from test_quick_exams import Api, login, question_body, subject, window


def png(width: int = 2, height: int = 2) -> bytes:
    """A valid grey PNG built with the standard library."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


PIXEL = base64.b64encode(png()).decode()
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def lines(document):
    return [
        (p.text, [bool(r.bold) for r in p.runs]) for p in document.paragraphs if p.text
    ]


async def test_exam_exports_as_docx(exams_app):
    async with PateraTestClient(exams_app) as client:
        teacher = Api(client, await login(client))
        other = Api(client, await login(client, "other@example.com"))
        client.client.cookies.clear()
        biology = await subject(teacher, "Biology")
        category = await teacher(
            "POST",
            "/api/categories/",
            201,
            json={"subject_id": biology["id"], "name": "Forces"},
        )
        first = await teacher(
            "POST",
            "/api/questions/",
            201,
            json=question_body(
                category,
                question_text=r"Koliko je $\frac{\sqrt{3}}{2} \cdot 2$?",
                answers=["1", r"$\sqrt{3}$", "2", "3"],
                correct_answer=1,
                image="data:image/png;base64," + PIXEL,
            ),
        )
        second = await teacher(
            "POST",
            "/api/questions/",
            201,
            json=question_body(
                category, question_text="Kaj je 2 + 2?", correct_answer=2
            ),
        )
        exam = await teacher(
            "POST",
            "/api/exams/",
            201,
            json={
                "subject_id": biology["id"],
                "title": "Kolokvij – sile",
                **window(),
                "question_ids": [second["id"], first["id"]],
            },
        )

        response = await client.get(
            f"/api/exams/{exam['id']}/docx", headers=teacher.headers
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith(DOCX)
        disposition = response.headers["content-disposition"]
        assert 'filename="Kolokvij_sile.docx"' in disposition
        assert "filename*=UTF-8''Kolokvij%20%E2%80%93%20sile.docx" in disposition

        document = Document(BytesIO(response.content))
        assert lines(document) == [
            ("Kolokvij – sile", [False]),
            ("1. Kaj je 2 + 2?", [False, False]),
            ("a) 3", [False]),
            ("b) 4", [False]),
            ("c) 5", [True]),
            ("d) 6", [False]),
            ("2. Koliko je √3/2 · 2?", [False, False]),
            ("a) 1", [False]),
            ("b) √3", [True]),
            ("c) 2", [False]),
            ("d) 3", [False]),
        ]
        assert len(document.inline_shapes) == 1  # the question image

        # An unreadable stored image is replaced by a note, not an error.
        await teacher(
            "PUT",
            f"/api/questions/{second['id']}",
            json=question_body(
                category,
                question_text="Kaj je 2 + 2?",
                correct_answer=2,
                image="data:image/png;base64,"
                + base64.b64encode(b"\x89PNG\r\n\x1a\nbroken").decode(),
            ),
        )
        response = await client.get(
            f"/api/exams/{exam['id']}/docx", headers=teacher.headers
        )
        assert response.status_code == 200
        assert "[Image could not be included]" in [
            p.text for p in Document(BytesIO(response.content)).paragraphs
        ]

        # Only the owner exports; unknown exams are 404.
        await other("GET", f"/api/exams/{exam['id']}/docx", 404)
        assert (await client.get(f"/api/exams/{exam['id']}/docx")).status_code == 401


async def test_random_per_attempt_exam_exports_a_drawn_version(exams_app):
    async with PateraTestClient(exams_app) as client:
        teacher = Api(client, await login(client))
        biology = await subject(teacher, "Biology")
        category = await teacher(
            "POST",
            "/api/categories/",
            201,
            json={"subject_id": biology["id"], "name": "Forces"},
        )
        questions = [
            await teacher(
                "POST",
                "/api/questions/",
                201,
                json=question_body(category, question_text=f"Vprašanje {n}?"),
            )
            for n in range(5)
        ]
        exam = await teacher(
            "POST",
            "/api/exams/",
            201,
            json={
                "subject_id": biology["id"],
                "title": "Random",
                **window(),
                "random": {
                    "category_ids": [category["id"]],
                    "count": 3,
                    "per_attempt": True,
                },
            },
        )
        response = await client.get(
            f"/api/exams/{exam['id']}/docx", headers=teacher.headers
        )
        assert response.status_code == 200
        numbered = [
            p.text
            for p in Document(BytesIO(response.content)).paragraphs
            if p.text[:2] in ("1.", "2.", "3.", "4.")
        ]
        assert len(numbered) == 3
        assert all(
            text.split(" ", 1)[1] in {q["question_text"] for q in questions}
            for text in numbered
        )

        for question in questions[:3]:
            await teacher("DELETE", f"/api/questions/{question['id']}", 204)
        response = await client.get(
            f"/api/exams/{exam['id']}/docx", headers=teacher.headers
        )
        assert response.status_code == 400
