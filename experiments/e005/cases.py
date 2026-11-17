"""Synthetic Pydantic v2 call-site corpus; examples are not imported by agents."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Case:
    identifier: str
    source: str
    runtime_accepts: bool
    rationale: str


CASES: tuple[Case, ...] = (
    Case(
        "strict_valid",
        """from pydantic import BaseModel, Field
class User(BaseModel):
    age: int = Field(strict=True)
assert User(age=42).age == 42
""",
        True,
        "Strict integer field accepts a true integer.",
    ),
    Case(
        "strict_string_invalid",
        """from pydantic import BaseModel, Field
class User(BaseModel):
    age: int = Field(strict=True)
User(age="42")
""",
        False,
        "Strict integer field must not coerce text.",
    ),
    Case(
        "lax_string_valid",
        """from pydantic import BaseModel
class User(BaseModel):
    age: int
assert User(age="42").age == 42
""",
        True,
        "Default lax integer field coerces a valid numeric string.",
    ),
    Case(
        "extra_ignore_valid",
        """from pydantic import BaseModel
class Entry(BaseModel):
    x: int
item = Entry(x=1, unrelated=2)
assert item.model_extra is None
assert not hasattr(item, "unrelated")
""",
        True,
        "Default extra='ignore' accepts but discards extra data; not extra='allow'.",
    ),
    Case(
        "extra_allow_valid",
        """from pydantic import BaseModel, ConfigDict
class Entry(BaseModel):
    model_config = ConfigDict(extra="allow")
    x: int
item = Entry(x=1, unrelated=2)
assert item.model_extra == {"unrelated": 2}
""",
        True,
        "Explicit extra='allow' retains extra values.",
    ),
    Case(
        "extra_forbid_invalid",
        """from pydantic import BaseModel, ConfigDict
class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int
Entry(x=1, unrelated=2)
""",
        False,
        "Explicit extra='forbid' rejects unknown constructor keywords.",
    ),
    Case(
        "frozen_assignment_invalid",
        """from pydantic import BaseModel, ConfigDict
class Entry(BaseModel):
    model_config = ConfigDict(frozen=True)
    x: int
item = Entry(x=1)
item.x = 2
""",
        False,
        "Frozen Pydantic fields cannot be reassigned.",
    ),
    Case(
        "field_constraint_valid",
        """from pydantic import BaseModel, Field
class Entry(BaseModel):
    score: int = Field(gt=0, lt=10)
assert Entry(score=5).score == 5
""",
        True,
        "Literal value falls within documented Pydantic field bounds.",
    ),
    Case(
        "field_constraint_invalid",
        """from pydantic import BaseModel, Field
class Entry(BaseModel):
    score: int = Field(gt=0, lt=10)
Entry(score=0)
""",
        False,
        "Literal zero violates gt=0; static constraint detection is optional.",
    ),
    Case(
        "optional_without_default_invalid",
        """from pydantic import BaseModel
class Entry(BaseModel):
    name: str | None
Entry()
""",
        False,
        "Optional annotation does not imply a default in Pydantic v2.",
    ),
    Case(
        "optional_default_valid",
        """from pydantic import BaseModel
class Entry(BaseModel):
    name: str | None = None
assert Entry().name is None
""",
        True,
        "Explicit None default makes the field omittable.",
    ),
    Case(
        "builtin_alias_generator_valid",
        """from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
class Entry(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel)
    first_name: str
assert Entry(firstName="Ada").first_name == "Ada"
""",
        True,
        "Pydantic's builtin to_camel alias is documented as recognized by Pyrefly.",
    ),
    Case(
        "custom_alias_generator_valid",
        """from pydantic import BaseModel, ConfigDict
def convert(name: str) -> str:
    return "x_" + name
class Entry(BaseModel):
    model_config = ConfigDict(alias_generator=convert)
    first_name: str
assert Entry(x_first_name="Ada").first_name == "Ada"
""",
        True,
        "Custom alias generators work at runtime; Pyrefly documents limited static support.",
    ),
    Case(
        "root_strict_invalid",
        """from pydantic import RootModel, StrictInt
class Value(RootModel[StrictInt]):
    pass
Value("42")
""",
        False,
        "RootModel[StrictInt] rejects a string.",
    ),
    Case(
        "pydantic_dataclass_lax_valid",
        """from pydantic.dataclasses import dataclass
@dataclass
class Entry:
    amount: int
assert Entry(amount="42").amount == 42
""",
        True,
        "Pydantic dataclasses can coerce compatible string input at runtime.",
    ),
    Case(
        "settings_default_valid",
        """from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    zone: str = "test-default"
assert Settings(_env_file=None).zone == "test-default"
""",
        True,
        "Simple pydantic-settings default, with external dotenv loading disabled.",
    ),
)
