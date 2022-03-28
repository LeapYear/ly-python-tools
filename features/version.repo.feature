Feature: The publish repo

    Scenario Outline: Get the publish repo
        Given the "pyproject.toml" file
            """
            [tool.poetry]
            name = "test-project"
            version = "<project_version>"
            description = ""
            authors = []

            [[tool.version.handlers]]
            repo = "my_repo"
            matchers = [{ env = "ENV", pattern = '^v(.*)$', validate = false }]
            extra = ".dev123+${EXTRA}"
            """
        And the env vars
            | name  | value  |
            | ENV   | v1.1.3 |
            | EXTRA | more   |
        When I run version with "--repo"
        Then stdout contains "my_repo"

        Examples:
            | project_version   | extra            |
            | 1.1.3             | .dev123+${EXTRA} |
            | 1.1.3.dev123+more | .dev123+${EXTRA} |
