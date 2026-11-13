from fastapi import FastAPI


def test_app_main_exposes_the_fastapi_app_vercel_loads():
    from app.main import app

    assert isinstance(app, FastAPI)
