from pydantic import BaseModel, ConfigDict


class ApiInfoResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "AI Architecture Platform API",
                    "version": "v1",
                    "contract": "/openapi.json",
                }
            ]
        }
    )
    name: str
    version: str
    contract: str
