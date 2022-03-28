Feature: Set the version

    Scenario Outline: Set version
        Given the "pyproject.toml" file
            """
            [tool.poetry]
            name = "test-project"
            version = "<project_version>"
            description = ""
            authors = []

            [tool.version]
            version_path = "version.py"
            pep440_check = true

            [[tool.version.handlers]]
            repo = "repo"
            matchers = [{ env = "ENV", pattern = '<pattern>', validate = <validate> }]
            extra = "<extra>"
            """
        And the "version.py" file
            """
            # Version file
            __version__ = "0.0.0"
            """
        And the env vars
            | name  | value       |
            | ENV   | <env_value> |
            | EXTRA | more        |
        When I run version with no arguments
        Then stdout contains "poetry version <final_version>"
        And stdout contains text
            """
            __version__ = "<final_version>"  # Auto-generated
            """
        And the file "pyproject.toml" contains text
            """
            version = "<final_version>"
            """
        And the file "version.py" contains text
            """
            __version__ = "<final_version>"  # Auto-generated
            """

        Examples:
            | project_version | env_value    | pattern                                 | extra            | validate | final_version     |
            | 1.1.3           | v1.2.3       | ^v(.*)$                                 |                  | false    | 1.1.3             |
            | 1.2.3           | v1.2.3       | ^v(.*)$                                 |                  | true     | 1.2.3             |
            | 1.2.3.post1     | v1.2.3.post1 | ^v((\d+)\.(\d+)\.(\d+)(\.post[0-9]+)?)$ |                  | true     | 1.2.3.post1       |
            | 1.1.3           | v1.2.3       | ^v(.*)$                                 | a123+abc         | false    | 1.1.3a123+abc     |
            | 1.1.3           | v1.2.3       | ^v(.*)$                                 | .dev123+${EXTRA} | false    | 1.1.3.dev123+more |
