"""
Domain Configuration Loader

Loads, validates, and manages domain configuration files (YAML).
Provides runtime access to domain-specific settings, node types, relationship types, and prompts.

Usage:
    from domain.config_loader import DomainConfigLoader

    loader = DomainConfigLoader("domains/it_skills.yaml")
    config = loader.load()

    # Access configuration
    print(config.metadata.name)
    print(config.node_types)
    print(config.get_prompt("densification", node_name="python"))
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from jinja2 import Template


@dataclass
class NodeTypeSchema:
    """Schema definition for a node type."""

    name: str
    display_name: str
    description: str
    schema: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate node type schema."""
        if not self.name.replace("_", "").isalnum():
            raise ValueError(f"Node type name must be alphanumeric with underscores: {self.name}")


@dataclass
class RelationshipTypeSchema:
    """Schema definition for a relationship type."""

    name: str
    display_name: str
    description: str
    source_types: List[str]
    target_types: List[str]
    properties: List[Dict[str, Any]] = field(default_factory=list)
    cardinality: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate relationship type schema."""
        if not self.name.replace("_", "").isalnum():
            raise ValueError(f"Relationship type name must be alphanumeric: {self.name}")

        valid_cardinalities = ["one_to_one", "one_to_many", "many_to_one", "many_to_many", None]
        if self.cardinality not in valid_cardinalities:
            raise ValueError(f"Invalid cardinality: {self.cardinality}")


@dataclass
class DomainMetadata:
    """Domain metadata."""

    name: str
    domain_id: str
    version: str
    description: str
    owner: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainMetadata":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            domain_id=data["domain_id"],
            version=data["version"],
            description=data["description"],
            owner=data["owner"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
        )


@dataclass
class DataSourceConfig:
    """Data source configuration."""

    name: str
    type: str
    enabled: bool
    path: Optional[str] = None
    encoding: str = "utf-8"
    delimiter: str = ","
    url: Optional[str] = None
    method: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    auth_type: Optional[str] = None
    connection_string: Optional[str] = None
    query: Optional[str] = None
    mappings: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class LLMConfig:
    """LLM configuration."""

    enabled: bool
    provider: str
    model: str
    api_key_env: str
    temperature: float
    max_tokens: int
    prompts: Dict[str, str] = field(default_factory=dict)


@dataclass
class ValidationConfig:
    """Validation rules configuration."""

    auto_approve_threshold: int
    min_alias_length: int
    max_alias_length: int
    allow_duplicates: bool
    require_relationships: bool
    custom_validators: List[str] = field(default_factory=list)


@dataclass
class DomainConfig:
    """
    Complete domain configuration.

    Loaded from YAML file and provides access to all domain-specific settings.
    """

    metadata: DomainMetadata
    node_types: List[NodeTypeSchema]
    relationship_types: List[RelationshipTypeSchema]
    data_sources: List[DataSourceConfig]
    llm: LLMConfig
    validation: ValidationConfig
    export: Dict[str, Any]
    cache: Dict[str, Any]
    webhooks: Dict[str, Any]
    extensions: Dict[str, Any]
    migration: Dict[str, Any]
    raw_config: Dict[str, Any]  # Original YAML data

    def get_node_type(self, name: str) -> Optional[NodeTypeSchema]:
        """Get node type by name."""
        for node_type in self.node_types:
            if node_type.name == name:
                return node_type
        return None

    def get_relationship_type(self, name: str) -> Optional[RelationshipTypeSchema]:
        """Get relationship type by name."""
        for rel_type in self.relationship_types:
            if rel_type.name == name:
                return rel_type
        return None

    def validate_relationship(self, rel_type_name: str, source_type: str, target_type: str) -> bool:
        """Validate if a relationship type can connect the given node types."""
        rel_type = self.get_relationship_type(rel_type_name)
        if not rel_type:
            return False

        return source_type in rel_type.source_types and target_type in rel_type.target_types

    def get_prompt(self, prompt_name: str, **template_vars: Any) -> str:
        """
        Render a prompt template with variables.

        Args:
            prompt_name: Name of the prompt (e.g., 'densification', 'suggestion')
            **template_vars: Variables to pass to the Jinja2 template

        Returns:
            Rendered prompt string

        Example:
            prompt = config.get_prompt(
                'densification',
                node_name='python',
                existing_nodes_sample=['javascript', 'java', 'c++']
            )
        """
        if prompt_name not in self.llm.prompts:
            raise ValueError(f"Prompt '{prompt_name}' not found in LLM configuration")

        template_str = self.llm.prompts[prompt_name]
        template = Template(template_str)

        # Add domain metadata and config to template context
        context = {
            "metadata": self.metadata,
            "node_types": self.node_types,
            "relationship_types": self.relationship_types,
            **template_vars,
        }

        return template.render(**context)

    def get_active_data_sources(self) -> List[DataSourceConfig]:
        """Get only enabled data sources."""
        return [ds for ds in self.data_sources if ds.enabled]


class DomainConfigLoader:
    """
    Loads and validates domain configuration files.

    Handles YAML parsing, schema validation, and error reporting.
    """

    def __init__(self, config_path: str):
        """
        Initialize loader with config file path.

        Args:
            config_path: Path to domain YAML file (absolute or relative)
        """
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"Domain config file not found: {config_path}")

    def load(self) -> DomainConfig:
        """
        Load and parse domain configuration.

        Returns:
            DomainConfig object

        Raises:
            ValueError: If configuration is invalid
            yaml.YAMLError: If YAML syntax is invalid
        """
        with open(self.config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        # Validate required sections
        required_sections = ["metadata", "node_types", "relationship_types", "llm", "validation"]
        for section in required_sections:
            if section not in raw_config:
                raise ValueError(f"Missing required section: {section}")

        # Parse metadata
        metadata = DomainMetadata.from_dict(raw_config["metadata"])

        # Parse node types
        node_types = [
            NodeTypeSchema(
                name=nt["name"],
                display_name=nt["display_name"],
                description=nt["description"],
                schema=nt.get("schema", []),
            )
            for nt in raw_config["node_types"]
        ]

        # Parse relationship types
        relationship_types = [
            RelationshipTypeSchema(
                name=rt["name"],
                display_name=rt["display_name"],
                description=rt["description"],
                source_types=rt["source_types"],
                target_types=rt["target_types"],
                properties=rt.get("properties", []),
                cardinality=rt.get("cardinality"),
            )
            for rt in raw_config["relationship_types"]
        ]

        # Validate relationship types reference valid node types
        node_type_names = {nt.name for nt in node_types}
        for rt in relationship_types:
            for source_type in rt.source_types:
                if source_type not in node_type_names:
                    raise ValueError(
                        f"Relationship '{rt.name}' references unknown source type: {source_type}"
                    )
            for target_type in rt.target_types:
                if target_type not in node_type_names:
                    raise ValueError(
                        f"Relationship '{rt.name}' references unknown target type: {target_type}"
                    )

        # Parse data sources
        data_sources = [
            DataSourceConfig(
                name=ds["name"],
                type=ds["type"],
                enabled=ds["enabled"],
                path=ds.get("path"),
                encoding=ds.get("encoding", "utf-8"),
                delimiter=ds.get("delimiter", ","),
                url=ds.get("url"),
                method=ds.get("method"),
                headers=ds.get("headers"),
                auth_type=ds.get("auth_type"),
                connection_string=ds.get("connection_string"),
                query=ds.get("query"),
                mappings=ds.get("mappings", []),
            )
            for ds in raw_config.get("data_sources", [])
        ]

        # Parse LLM config
        llm_data = raw_config["llm"]
        llm = LLMConfig(
            enabled=llm_data["enabled"],
            provider=llm_data["provider"],
            model=llm_data["model"],
            api_key_env=llm_data["api_key_env"],
            temperature=llm_data["temperature"],
            max_tokens=llm_data["max_tokens"],
            prompts=llm_data.get("prompts", {}),
        )

        # Parse validation config
        val_data = raw_config["validation"]
        validation = ValidationConfig(
            auto_approve_threshold=val_data["auto_approve_threshold"],
            min_alias_length=val_data["min_alias_length"],
            max_alias_length=val_data["max_alias_length"],
            allow_duplicates=val_data["allow_duplicates"],
            require_relationships=val_data["require_relationships"],
            custom_validators=val_data.get("custom_validators", []),
        )

        return DomainConfig(
            metadata=metadata,
            node_types=node_types,
            relationship_types=relationship_types,
            data_sources=data_sources,
            llm=llm,
            validation=validation,
            export=raw_config.get("export", {}),
            cache=raw_config.get("cache", {}),
            webhooks=raw_config.get("webhooks", {}),
            extensions=raw_config.get("extensions", {}),
            migration=raw_config.get("migration", {}),
            raw_config=raw_config,
        )


class DomainConfigManager:
    """
    Manages multiple domain configurations.

    Provides centralized access to domain configs, caching, and validation.
    """

    def __init__(self) -> None:
        """Initialize manager."""
        self._configs: Dict[str, DomainConfig] = {}

    def load_domain(self, config_path: str) -> DomainConfig:
        """
        Load a domain configuration.

        Args:
            config_path: Path to domain YAML file

        Returns:
            DomainConfig object
        """
        loader = DomainConfigLoader(config_path)
        config = loader.load()
        self._configs[config.metadata.domain_id] = config
        return config

    def get_domain(self, domain_id: str) -> Optional[DomainConfig]:
        """Get loaded domain by ID."""
        return self._configs.get(domain_id)

    def list_domains(self) -> List[str]:
        """List all loaded domain IDs."""
        return list(self._configs.keys())

    @classmethod
    def from_env(cls, env_var: str = "DOMAIN_CONFIG_PATH") -> "DomainConfigManager":
        """
        Create manager and load domain from environment variable.

        Args:
            env_var: Environment variable containing path to domain config

        Returns:
            DomainConfigManager with loaded domain

        Raises:
            ValueError: If environment variable not set
        """
        config_path = os.getenv(env_var)
        if not config_path:
            raise ValueError(f"Environment variable {env_var} not set")

        manager = cls()
        manager.load_domain(config_path)
        return manager
