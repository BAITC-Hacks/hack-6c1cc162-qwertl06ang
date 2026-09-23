"use strict";

// Все запросы идут к тому же FastAPI, который отдал эту страницу.
// Ни ключей API, ни обращений к внешним сервисам здесь нет.
const form = document.getElementById("recommend-form");
const fields = document.getElementById("form-fields");
const resultsSection = document.getElementById("results-section");
const submitButton = document.getElementById("submit-button");
const submitLabel = document.getElementById("submit-label");
const catalogStatus = document.getElementById("catalog-status");
const retryButton = document.getElementById("retry-button");
const cards = document.getElementById("cards");
const counter = document.getElementById("result-counter");
const querySummary = document.getElementById("query-summary");
const changedNotice = document.getElementById("changed-notice");
const algorithmNote = document.getElementById("algorithm-note");
const exampleButtons = [...document.querySelectorAll("[data-example]")];
const money = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });

const inputs = {
    city: document.getElementById("city"),
    event_date: document.getElementById("event-date"),
    event_type: document.getElementById("event-type"),
    category: document.getElementById("category"),
    budget: document.getElementById("budget"),
    duration: document.getElementById("duration"),
    language: document.getElementById("language"),
    preferences: document.getElementById("preferences"),
};
const labels = {
    city: "Город", event_date: "Дата", event_type: "Тип мероприятия",
    category: "Категория", budget: "Бюджет", duration: "Длительность", language: "Язык", preferences: "Пожелания",
};
const defaultQuery = {
    city: "Алматы", event_date: "2026-11-13", event_type: "свадьба",
    category: "Фотограф", budget: 500000, duration: 4, language: "русский", preferences: "",
};
const examples = {
    success: {},
    emotions: { preferences: "Живые эмоции и ненавязчивая свадебная съёмка" },
    concerts: { preferences: "Опыт съёмки концертов, сцены и выступлений артистов" },
    busy: { event_date: "2026-11-14" },
    rare: { category: "Флорист" },
    budget: { budget: 100000 },
    absent: { city: "Астана", category: "Декоратор" },
};
let ready = false;
let busy = false;
let hasResult = false;

function showStatus(kind, title, message) {
    document.getElementById("result-status").className = `status-box ${kind}`;
    document.getElementById("status-title").textContent = title;
    document.getElementById("status-message").textContent = message;
}

function formatDate(value) {
    // Переставляем части ISO-даты без преобразований часового пояса.
    return value.split("-").reverse().join(".");
}

function setControls() {
    fields.disabled = !ready || busy;
    exampleButtons.forEach((button) => { button.disabled = !ready || busy; });
    submitButton.classList.toggle("loading", busy);
    submitLabel.textContent = busy ? "Подбираем…" : "Подобрать подрядчиков";
    resultsSection.setAttribute("aria-busy", String(busy));
}

function fillSelect(select, values, optional = false) {
    select.replaceChildren();
    if (optional) select.add(new Option("Не важно", ""));
    values.forEach((value) => select.add(new Option(value, value)));
}

function applyQuery(query) {
    Object.entries(inputs).forEach(([key, input]) => {
        const value = String(query[key] ?? "");
        if (input.tagName === "SELECT") {
            const exists = [...input.options].some((option) => option.value === value);
            input.value = exists ? value : input.options[0]?.value ?? "";
        } else {
            input.value = value;
        }
    });
}

function getErrorMessage(response, data) {
    if (response.status === 404) {
        return "Нужный адрес API не найден. Проверьте, что app.py заменён файлом обновления CSV, и перезапустите сервер.";
    }
    if (Array.isArray(data?.detail)) {
        const names = [...new Set(data.detail.map((error) => {
            const key = error.loc?.[error.loc.length - 1];
            return labels[key] ?? key ?? "параметры запроса";
        }))];
        return `Проверьте поля: ${names.join(", ")}. Дата должна быть в указанном диапазоне; бюджет — целым неотрицательным числом; длительность — положительным числом.`;
    }
    if (typeof data?.detail === "string") return data.detail;
    return `Сервер вернул ошибку ${response.status}. Проверьте терминал VS Code.`;
}

async function requestJSON(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12000);
    try {
        const response = await fetch(path, { ...options, signal: controller.signal });
        const data = await response.json().catch(() => null);
        if (!response.ok) throw new Error(getErrorMessage(response, data));
        if (data === null) throw new Error("Сервер вернул ответ не в формате JSON.");
        return data;
    } catch (error) {
        if (error.name === "AbortError") {
            throw new Error("Сервер не ответил за 12 секунд. Проверьте терминал и повторите запрос.");
        }
        if (error instanceof TypeError) {
            throw new Error("Нет соединения с сервером. Запустите Uvicorn в VS Code и откройте сайт через http://127.0.0.1:8000.");
        }
        throw error;
    } finally {
        clearTimeout(timer);
    }
}

async function loadOptions() {
    ready = false;
    setControls();
    retryButton.hidden = true;
    catalogStatus.className = "catalog-status";
    catalogStatus.textContent = "Загружаем каталог…";
    try {
        if (location.protocol === "file:") {
            throw new Error("Не открывайте index.html двойным щелчком. Запустите сервер и откройте http://127.0.0.1:8000.");
        }
        const data = await requestJSON("/options");
        for (const key of ["cities", "categories", "event_types", "languages"]) {
            if (!Array.isArray(data[key])) throw new Error("Неверный ответ /options. Проверьте версию app.py.");
        }
        fillSelect(inputs.city, data.cities);
        fillSelect(inputs.category, data.categories);
        fillSelect(inputs.event_type, data.event_types);
        fillSelect(inputs.language, data.languages, true);
        inputs.event_date.min = data.date_min;
        inputs.event_date.max = data.date_max;
        document.getElementById("date-hint").textContent = `Календарь: ${formatDate(data.date_min)} — ${formatDate(data.date_max)}.`;
        applyQuery(defaultQuery);
        catalogStatus.textContent = `Каталог загружен · профилей: ${data.count} · синтетических: ${data.synthetic_count}`;
        const aiStatus = document.getElementById("ai-status");
        aiStatus.textContent = data.ai?.message ?? "Нет информации об AI. Проверьте app.py.";
        aiStatus.classList.toggle("error", !data.ai?.ready);
        ready = true;
        showStatus("neutral", "Здесь появится подборка", "Заполните форму слева или запустите один из примеров ниже.");
    } catch (error) {
        catalogStatus.classList.add("error");
        catalogStatus.textContent = "Каталог не загружен.";
        showStatus("error", "Ошибка загрузки каталога", error.message);
        retryButton.hidden = false;
    } finally {
        setControls();
    }
}

// Данные вставляются как текст, а не как исполняемый HTML.
function makeElement(tag, className, text) {
    const element = document.createElement(tag);
    element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
}

function buildCard(profile) {
    const card = makeElement("article", "card");
    card.dataset.id = String(profile.id);
    const top = makeElement("div", "card-top");
    const heading = makeElement("div", "card-heading");
    heading.append(makeElement("p", "card-category", profile.category));
    heading.append(makeElement("h3", "", profile.name));
    const price = makeElement("div", "card-price", `от ${money.format(profile.price_from_kzt)} ₸`);
    price.append(makeElement("span", "price-label", "за мероприятие"));
    top.append(heading, price);
    const meta = makeElement("div", "card-meta");
    meta.append(makeElement("span", "tag", profile.city));
    meta.append(makeElement("span", "tag", "Из загруженного CSV"));
    if (profile.synthetic) meta.append(makeElement("span", "tag synthetic", "Синтетический профиль"));
    if (profile.city_imputed) meta.append(makeElement("span", "tag", "Город дополнен при подготовке данных"));
    if (profile.price_imputed) meta.append(makeElement("span", "tag", "Цена дополнена при подготовке данных"));
    card.append(top, meta, makeElement("p", "reason-label", "Почему подходит"), makeElement("p", "reason", profile.reason));
    return card;
}

function displayResult(data) {
    algorithmNote.textContent = data.ranking_note ?? "Режим сортировки не указан.";
    algorithmNote.hidden = false;
    algorithmNote.classList.toggle("fallback", data.ranking_mode === "rules_fallback");
    if (!["found", "no_category", "no_match"].includes(data.status) || !Array.isArray(data.results)) {
        throw new Error("Неожиданный ответ сервера. Проверьте app.py и recommender.py из предыдущих шагов.");
    }
    if (data.status === "found") {
        showStatus("success", "Подрядчики подобраны", data.message);
        data.results.slice(0, 3).forEach((profile) => cards.append(buildCard(profile)));
        counter.textContent = `Показано ${Math.min(data.results.length, 3)} из ${data.total_matches}`;
        counter.hidden = false;
        algorithmNote.hidden = false;
    } else if (data.status === "no_category") {
        showStatus("warning", "Такой категории в городе нет", `${data.message} Выберите другой город или категорию.`);
    } else {
        showStatus("warning", "Никто не проходит условия", `${data.message} Попробуйте другую дату или измените условия вручную.`);
    }
}

async function handleSubmit(event) {
    event.preventDefault();
    if (!ready || busy || !form.reportValidity()) return;
    const query = {
        city: inputs.city.value,
        event_date: inputs.event_date.value,
        event_type: inputs.event_type.value,
        category: inputs.category.value,
        budget: Number(inputs.budget.value),
        duration: inputs.duration.value === "" ? null : Number(inputs.duration.value),
        language: inputs.language.value || null,
        preferences: inputs.preferences.value.trim(),
    };
    cards.replaceChildren();
    counter.hidden = true;
    algorithmNote.hidden = true;
    changedNotice.hidden = true;
    hasResult = false;
    if (!Number.isSafeInteger(query.budget) || query.budget < 0) {
        querySummary.hidden = true;
        showStatus("error", "Проверьте бюджет", "Введите целую неотрицательную сумму без пробелов и знака валюты.");
        return;
    }
    const summary = [query.city, formatDate(query.event_date), query.event_type, query.category, `до ${money.format(query.budget)} ₸`];
    if (query.duration !== null) summary.push(`${query.duration} ч`);
    if (query.language !== null) summary.push(query.language);
    if (query.preferences) summary.push(`Пожелания: ${query.preferences}`);
    querySummary.textContent = summary.join(" · ");
    querySummary.hidden = false;
    busy = true;
    setControls();
    showStatus("neutral", "Подбираем подрядчиков…", "Проверяем дату, бюджет и остальные условия.");
    try {
        const data = await requestJSON("/recommend", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(query),
        });
        displayResult(data);
        hasResult = true;
    } catch (error) {
        cards.replaceChildren();
        counter.hidden = true;
        algorithmNote.hidden = true;
        showStatus("error", "Ошибка запроса", error.message);
    } finally {
        busy = false;
        setControls();
    }
}

form.addEventListener("submit", handleSubmit);
form.addEventListener("input", () => { if (hasResult) changedNotice.hidden = false; });
form.addEventListener("change", () => { if (hasResult) changedNotice.hidden = false; });
retryButton.addEventListener("click", loadOptions);
exampleButtons.forEach((button) => {
    button.addEventListener("click", () => {
        if (!ready || busy) return;
        applyQuery({ ...defaultQuery, ...examples[button.dataset.example] });
        form.requestSubmit();
        resultsSection.scrollIntoView({ block: "start" });
    });
});
loadOptions();
