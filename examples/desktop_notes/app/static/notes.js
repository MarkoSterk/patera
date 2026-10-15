// The notes page: a plain web page that talks to the JSON API in
// app/api/notes_api.py. It works the same in the desktop window and in a
// browser (`patera dev`).
"use strict";

const API = document.body.dataset.api.replace(/\/$/, "");
const SAVE_DELAY = 500; // milliseconds after the last keystroke

const list = document.getElementById("note-list");
const emptyList = document.getElementById("empty-list");
const search = document.getElementById("search");
const form = document.getElementById("note-form");
const placeholder = document.getElementById("placeholder");
const title = document.getElementById("title");
const body = document.getElementById("body");
const status = document.getElementById("status");
const deleteButton = document.getElementById("delete");

let notes = [];
let selectedId = null;
let saveTimer = null;
let searchTimer = null;

async function request(method, url, data) {
    const options = { method, headers: { Accept: "application/json" } };
    if (data !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(data);
    }
    const response = await fetch(url, options);
    if (!response.ok) {
        let message = response.statusText;
        try {
            message = (await response.json()).message || message;
        } catch (error) {
            // not a JSON error body
        }
        throw new Error(message);
    }
    return response.status === 204 ? null : response.json();
}

function describe(note) {
    const when = new Date(note.updated_at).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
    });
    const firstLine = note.body.trim().split("\n")[0];
    return firstLine ? `${when} · ${firstLine}` : when;
}

function renderList() {
    list.replaceChildren();
    for (const note of notes) {
        const item = document.createElement("li");
        item.dataset.id = note.id;
        item.classList.toggle("selected", note.id === selectedId);
        const name = document.createElement("div");
        name.className = "note-title";
        name.textContent = note.title || "Untitled";
        const meta = document.createElement("div");
        meta.className = "note-meta";
        meta.textContent = describe(note);
        item.append(name, meta);
        item.addEventListener("click", () => select(note.id));
        list.append(item);
    }
    emptyList.hidden = notes.length > 0 || search.value.trim() !== "";
}

function showEditor(note) {
    form.hidden = !note;
    placeholder.hidden = Boolean(note);
    if (note) {
        title.value = note.title;
        body.value = note.body;
        status.textContent = "";
        resetDelete();
    }
}

async function load() {
    const query = search.value.trim();
    const url = query ? `${API}/?q=${encodeURIComponent(query)}` : `${API}/`;
    notes = await request("GET", url);
    renderList();
}

async function select(id) {
    await saveNow();
    selectedId = id;
    renderList();
    showEditor(notes.find((note) => note.id === id));
}

async function createNote() {
    await saveNow();
    const note = await request("POST", `${API}/`, { title: "", body: "" });
    search.value = "";
    await load();
    await select(note.id);
    title.focus();
}

function scheduleSave() {
    status.textContent = "Editing…";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, SAVE_DELAY);
}

async function saveNow() {
    if (saveTimer === null || selectedId === null) {
        return;
    }
    clearTimeout(saveTimer);
    saveTimer = null;
    const id = selectedId;
    try {
        const saved = await request("PUT", `${API}/${id}`, {
            title: title.value,
            body: body.value,
        });
        notes = [saved, ...notes.filter((note) => note.id !== saved.id)];
        renderList();
        if (id === selectedId) {
            status.textContent = "Saved";
        }
    } catch (error) {
        if (id === selectedId) {
            status.textContent = `Not saved: ${error.message}`;
        }
    }
}

// Deleting takes two clicks: the button asks for confirmation first.
let confirmTimer = null;

function resetDelete() {
    clearTimeout(confirmTimer);
    deleteButton.classList.remove("confirm");
    deleteButton.textContent = "Delete";
}

async function deleteNote() {
    if (!deleteButton.classList.contains("confirm")) {
        deleteButton.classList.add("confirm");
        deleteButton.textContent = "Delete?";
        confirmTimer = setTimeout(resetDelete, 3000);
        return;
    }
    resetDelete();
    clearTimeout(saveTimer);
    saveTimer = null;
    await request("DELETE", `${API}/${selectedId}`);
    selectedId = null;
    showEditor(null);
    await load();
}

title.addEventListener("input", scheduleSave);
body.addEventListener("input", scheduleSave);
document.getElementById("new-note").addEventListener("click", createNote);
deleteButton.addEventListener("click", deleteNote);
search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(load, 200);
});
document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        createNote();
    }
});
window.addEventListener("beforeunload", () => saveNow());

load().then(() => {
    if (notes.length > 0) {
        select(notes[0].id);
    }
});
