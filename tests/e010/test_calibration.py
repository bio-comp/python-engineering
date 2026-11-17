"""Exposed calibration case only; never a blinded retrieval-efficacy trial."""

from typing import Self

import pydantic
import pytest
from pydantic import BaseModel, ValidationError, model_validator


class Interval(BaseModel):
    left: int
    right: int

    @model_validator(mode="after")
    def check(self) -> Self:
        if self.left >= self.right:
            raise ValueError("left must be smaller")
        return self


class KnownBadNoCrossFieldCheck(BaseModel):
    left: int
    right: int

    @model_validator(mode="after")
    def check(self) -> Self:
        return self


def test_pinned_calibration_acceptance_and_known_bad() -> None:
    assert pydantic.__version__ == "2.14.1"
    assert isinstance(Interval.model_validate({"left": 1, "right": 2}), Interval)
    with pytest.raises(ValidationError):
        Interval.model_validate({"left": 2, "right": 1})
    assert isinstance(
        KnownBadNoCrossFieldCheck.model_validate({"left": 2, "right": 1}),
        KnownBadNoCrossFieldCheck,
    )
