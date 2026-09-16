from src.application.logger import setup_logger


def test_logger_idempotence():
    logger1 = setup_logger()
    logger2 = setup_logger()

    assert logger1 is logger2
    assert len(logger1.handlers) > 0  # Asegura que se aadieron handlers, pero no se duplican
