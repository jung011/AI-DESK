"""settings Pydantic schemas — Spring VO 와 1:1."""
from pydantic import BaseModel, ConfigDict, Field


class A2aWorkspaceRs(BaseModel):
    path: str


class A2aWorkspaceRq(BaseModel):
    path: str
    purge_previous_history: bool = Field(default=False, alias="purgePreviousHistory")

    model_config = ConfigDict(populate_by_name=True)


class CodeServerRs(BaseModel):
    url: str
    alive: bool


class WorkroleFileRs(BaseModel):
    path: str


class WorkroleFileRq(BaseModel):
    path: str
