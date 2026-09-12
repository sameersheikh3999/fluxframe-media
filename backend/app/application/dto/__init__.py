"""Data Transfer Objects — plain dataclasses that cross the application boundary.

These are deliberately NOT Pydantic models. A Pydantic model is a validation and
serialisation tool, which makes it a transport concern; the moment a DTO grows a
``Field(alias=...)`` for the sake of a JSON payload, the application layer has
started caring about HTTP. Keeping DTOs as dataclasses makes that impossible.

The API layer maps Pydantic request schema -> DTO on the way in, and
DTO -> Pydantic response schema on the way out.
"""
