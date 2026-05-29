"""
Query Knowledge Base Loader

This module loads sample queries from the queries/ folder to help
the AI understand database schema and generate better SQL queries.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any


class QueryKnowledgeBase:
    """Loads and manages the query knowledge base"""

    def __init__(self, queries_dir: str = "queries"):
        self.queries_dir = Path(queries_dir)
        self.examples_dir = self.queries_dir / "examples"
        self.templates_dir = self.queries_dir / "templates"

    def load_all_queries(self) -> Dict[str, List[Dict[str, Any]]]:
        """Load all queries from the knowledge base"""
        return {
            'examples': self.load_examples(),
            'templates': self.load_templates()
        }

    def load_examples(self) -> List[Dict[str, Any]]:
        """Load example queries from the examples folder

        Priority order:
        1. brand_* files (universal, applicable to all brands)
        2. Other files (brand-specific, legacy)
        """
        examples = []

        if not self.examples_dir.exists():
            return examples

        all_files = list(self.examples_dir.glob("*.md"))

        # Sort files: prioritize brand_* files first
        def priority_sort_key(path):
            name = path.name.lower()
            if name.startswith('brand_'):
                return (0, name)  # Highest priority
            elif name.startswith('universal_'):
                return (1, name)  # Second priority
            else:
                return (2, name)  # Lower priority (legacy/brand-specific)

        sorted_files = sorted(all_files, key=priority_sort_key)

        for file_path in sorted_files:
            if file_path.name.startswith('_'):
                continue  # Skip template files

            try:
                query_data = self._parse_query_file(file_path)
                if query_data:
                    examples.append(query_data)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")

        print(f"✓ Loaded {len(examples)} query examples (priority: brand_* files first)")
        return examples

    def load_templates(self) -> List[Dict[str, Any]]:
        """Load query templates from the templates folder"""
        templates = []

        if not self.templates_dir.exists():
            return templates

        for file_path in self.templates_dir.glob("*.md"):
            try:
                template_data = self._parse_query_file(file_path)
                if template_data:
                    templates.append(template_data)
            except Exception as e:
                print(f"Error loading {file_path}: {e}")

        return templates

    def _parse_query_file(self, file_path: Path) -> Dict[str, Any]:
        """Parse a markdown query file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract frontmatter
        frontmatter = {}
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1].strip()
                content = parts[2].strip()

                # Parse frontmatter (simple YAML parsing)
                for line in frontmatter_text.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()

                        # Parse lists
                        if value.startswith('[') and value.endswith(']'):
                            value = [v.strip() for v in value[1:-1].split(',')]

                        frontmatter[key] = value

        # Extract SQL query
        sql_pattern = r'```sql\n(.*?)```'
        sql_matches = re.findall(sql_pattern, content, re.DOTALL)
        sql_query = sql_matches[0].strip() if sql_matches else None

        # Extract sections
        sections = self._extract_sections(content)

        return {
            'file': file_path.name,
            'metadata': frontmatter,
            'sql': sql_query,
            'description': sections.get('description', ''),
            'natural_language_examples': sections.get('natural_language', []),
            'output_columns': sections.get('output_columns', ''),
            'business_context': sections.get('business_context', ''),
            'full_content': content
        }

    def _extract_sections(self, content: str) -> Dict[str, Any]:
        """Extract different sections from markdown content"""
        sections = {}

        # Extract description
        desc_pattern = r'## Description\n(.*?)(?=\n##|\Z)'
        desc_match = re.search(desc_pattern, content, re.DOTALL)
        if desc_match:
            sections['description'] = desc_match.group(1).strip()

        # Extract natural language examples
        nl_pattern = r'## Sample Natural Language Questions\n(.*?)(?=\n##|\Z)'
        nl_match = re.search(nl_pattern, content, re.DOTALL)
        if nl_match:
            examples = []
            for line in nl_match.group(1).split('\n'):
                line = line.strip()
                if line.startswith('-') or line.startswith('*'):
                    examples.append(line.lstrip('-*').strip().strip('"\''))
            sections['natural_language'] = examples

        # Extract output columns
        output_pattern = r'## Expected Output Columns\n(.*?)(?=\n##|\Z)'
        output_match = re.search(output_pattern, content, re.DOTALL)
        if output_match:
            sections['output_columns'] = output_match.group(1).strip()

        # Extract business context
        context_pattern = r'## Business Context.*?\n(.*?)(?=\n##|\Z)'
        context_match = re.search(context_pattern, content, re.DOTALL)
        if context_match:
            sections['business_context'] = context_match.group(1).strip()

        return sections

    def get_context_for_ai(self) -> str:
        """
        Generate a formatted context string for the AI to understand
        the database schema and query patterns
        """
        queries = self.load_all_queries()

        context = "# Database Query Knowledge Base\n\n"

        # Add examples
        if queries['examples']:
            context += "## Example Queries\n\n"
            for i, example in enumerate(queries['examples'], 1):
                context += f"### Example {i}: {example['metadata'].get('description', 'Query')}\n\n"

                if example['description']:
                    context += f"{example['description']}\n\n"

                if example['metadata'].get('tables'):
                    tables = example['metadata']['tables']
                    if isinstance(tables, list):
                        context += f"**Tables used:** {', '.join(tables)}\n\n"

                if example['sql']:
                    context += f"```sql\n{example['sql']}\n```\n\n"

                if example['natural_language_examples']:
                    context += "**Natural language examples:**\n"
                    for nl in example['natural_language_examples']:
                        context += f"- {nl}\n"
                    context += "\n"

        # Add templates
        if queries['templates']:
            context += "\n## Query Templates\n\n"
            for template in queries['templates']:
                if template['metadata'].get('pattern'):
                    context += f"### Pattern: {template['metadata']['pattern']}\n\n"

                if template['sql']:
                    context += f"```sql\n{template['sql']}\n```\n\n"

        return context

    def search_queries(self, keyword: str) -> List[Dict[str, Any]]:
        """Search for queries containing a keyword"""
        all_queries = self.load_all_queries()
        results = []

        keyword_lower = keyword.lower()

        for example in all_queries['examples']:
            # Search in description, SQL, and metadata
            if (keyword_lower in str(example.get('description', '')).lower() or
                keyword_lower in str(example.get('sql', '')).lower() or
                keyword_lower in str(example.get('metadata', {})).lower()):
                results.append(example)

        return results


# Convenience function
def get_query_context() -> str:
    """Get the query context for AI"""
    kb = QueryKnowledgeBase()
    return kb.get_context_for_ai()


if __name__ == "__main__":
    # Test the loader
    kb = QueryKnowledgeBase()
    queries = kb.load_all_queries()

    print(f"Loaded {len(queries['examples'])} example queries")
    print(f"Loaded {len(queries['templates'])} templates")

    print("\n" + "="*50)
    print("Context for AI:")
    print("="*50)
    print(kb.get_context_for_ai())
