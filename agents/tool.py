from abc import ABC, abstractmethod
from typing import Type
from pydantic import BaseModel


class Tool(ABC):
    """Base class for building OpenAI tools"""

    Arguments: Type[BaseModel] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the tool"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Context for the agent: describe what the tool does, when to use it, and examples."""
        pass

    @abstractmethod
    def execute(self, arguments: BaseModel) -> dict:
        pass

    @staticmethod
    def _resolve_refs(schema, defs: dict):
        """
        Recursively resolve all $ref references in a schema by inlining the definitions.
        This makes the schema fully expanded so models can see all nested structures.
        """
        if isinstance(schema, dict):
            # If this is a $ref, replace it with the resolved definition
            if "$ref" in schema:
                ref_path = schema["$ref"]
                if ref_path.startswith("#/$defs/"):
                    def_name = ref_path.replace("#/$defs/", "")
                    if def_name in defs:
                        # Recursively resolve the referenced definition
                        # (it might contain more $refs)
                        resolved_def = Tool._resolve_refs(defs[def_name], defs)
                        return resolved_def
                # If we can't resolve, return as-is
                return schema

            # Otherwise, recursively resolve all nested values
            result = {}
            for key, value in schema.items():
                result[key] = Tool._resolve_refs(value, defs)
            return result

        elif isinstance(schema, list):
            # Recursively resolve all items in the list
            return [Tool._resolve_refs(item, defs) for item in schema]

        else:
            # Primitive value, return as-is
            return schema

    def get_parameters_schema(self) -> dict:
        """
        Generate the JSON schema for the tool's parameters.
        Automatically built from the Arguments Pydantic model.
        All $ref references are fully inlined so the model sees the complete schema.
        """
        if self.Arguments is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must define an Arguments class"
            )

        schema = self.Arguments.model_json_schema()

        properties = schema.get("properties", {})
        required = schema.get("required", [])
        defs = schema.get("$defs", {})

        resolved_properties = self._resolve_refs(properties, defs)

        openai_schema = {"type": "object", "properties": resolved_properties}

        if required:
            openai_schema["required"] = required

        return openai_schema

    def to_openai_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_parameters_schema(),
            },
        }

    def __call__(self, **kwargs) -> dict:
        """Allow the tool to be called directly with automatic validation"""
        if self.Arguments is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must define an Arguments class"
            )

        arguments = self.Arguments(**kwargs)
        return self.execute(arguments)
