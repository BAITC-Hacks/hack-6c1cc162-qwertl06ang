from contextlib import asynccontextmanager
import logging

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from recommender import (
    CALENDAR_START, CALENDAR_END, dataset_summary,
    load_contractors, recommend_contractors,
)


from semantic import engine


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATE_MIN = CALENDAR_START
DATE_MAX = CALENDAR_END

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Индекс готовится перед приёмом запросов. Модель здесь не скачивается.
    try:
        engine.initialize(load_contractors())
    except (OSError, ValueError) as error:
        logging.getLogger(__name__).warning("CSV не загружен при запуске: %s", error)
    print(engine.status()["message"], flush=True)
    yield


app = FastAPI(
    title="HackAlem API",
    description="Подбор по загруженному анонимизированному CSV. Не сервис бронирования.",
    version="0.5.0",
    lifespan=lifespan,
)

# Публикуем только static, а не папку проекта с .env и данными.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class RecommendRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    city: str = Field(min_length=1, max_length=100)
    event_date: date = Field(
        ge=DATE_MIN,
        le=DATE_MAX,
        description="Дата мероприятия: от 2026-09-23 до 2026-12-31.",
    )
    event_type: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    budget: int = Field(ge=0, le=9007199254740991)
    duration: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    language: str | None = Field(default=None, min_length=1, max_length=100)
    preferences: str = Field(
        default="", max_length=500,
        description="Необязательные пожелания к стилю. Не заменяют дату, бюджет и другие фильтры.",
    )


@app.get("/", response_class=FileResponse, include_in_schema=False)
def home() -> FileResponse:
    """Главная страница теперь возвращает сайт, а не JSON."""
    page = STATIC_DIR / "index.html"
    if not page.is_file():
        raise HTTPException(status_code=500, detail="Не найден static/index.html.")
    return FileResponse(page, headers={"Cache-Control": "no-store"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ai/status", summary="Готовность локальной AI-модели")
def ai_status() -> dict[str, Any]:
    return engine.status()


@app.get("/contractors")
def get_contractors() -> dict[str, Any]:
    try:
        contractors = load_contractors()
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {
        **dataset_summary(contractors),
        "contractors": contractors,
    }


@app.get("/options", summary="Варианты для полей формы")
def get_options() -> dict[str, Any]:
    """Варианты берём из каталога, а не дублируем вручную в HTML."""
    try:
        contractors = load_contractors()
        cities = sorted({item["city"] for item in contractors})
        categories = sorted({v for item in contractors for v in item["categories"]})
        event_types = sorted({v for item in contractors for v in item["event_formats"]})
        languages = sorted({v for item in contractors for v in item["languages"]})
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {
        **dataset_summary(contractors),
        "ai": engine.status(),
        "cities": cities,
        "categories": categories,
        "event_types": event_types,
        "languages": languages,
        "date_min": DATE_MIN.isoformat(),
        "date_max": DATE_MAX.isoformat(),
    }


@app.post("/recommend", summary="Подобрать подрядчиков")
def recommend(request: RecommendRequest) -> dict[str, Any]:
    try:
        return recommend_contractors(request.model_dump(mode="json"))
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
