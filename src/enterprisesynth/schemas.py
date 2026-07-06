from __future__ import annotations

from pydantic import BaseModel, Field


class Parameter(BaseModel):
    name: str
    location: str  # path, query, header, cookie
    required: bool = False
    schema_type: str | None = None


class Endpoint(BaseModel):
    path: str
    method: str
    operation_id: str | None = None
    parameters: list[Parameter] = Field(default_factory=list)
    request_body_required: bool = False
    request_body_schema_present: bool = False
    response_schemas: dict[str, bool] = Field(default_factory=dict)  # status code -> schema present
    auth_schemes: list[str] = Field(default_factory=list)


class APISchema(BaseModel):
    title: str
    version: str
    endpoints: list[Endpoint] = Field(default_factory=list)
    global_auth_schemes: list[str] = Field(default_factory=list)
