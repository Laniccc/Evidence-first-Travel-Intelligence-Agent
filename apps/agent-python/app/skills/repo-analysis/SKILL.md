---
name: repo-analysis
description: Analyze a GitHub repository or project structure for architecture, entry points, and code quality.
triggers: github,repo,repository,codebase,仓库,源代码,项目结构,architecture review,analyze repo
---

# Repo Analysis Skill

Use this skill when the user asks about a GitHub repository, local project folder, or codebase.

## Workflow

1. **Start with documentation**: Read README, CONTRIBUTING, or project docs first to understand intent.
2. **Build a structural map**:
   - Language, package manager, build system
   - Dependency files (requirements.txt, package.json, pom.xml, Cargo.toml, etc.)
   - Scripts (build, test, deploy)
   - Config files and environment setup
   - Entry points (main, CLI, API routes, server startup)
3. **Identify key modules**: Group source files by responsibility (models, services, controllers, utils, etc.).
4. **Trace execution paths**: For a given feature or request, identify which files are involved.
5. **Read only what's needed**: Avoid dumping entire files. Read specific functions or classes that support the user's question.
6. **Check for quality issues**:
   - Missing tests or low coverage areas
   - Hard-coded paths, secrets, or configuration
   - Unpinned dependencies
   - Missing error handling
   - Circular imports or tight coupling
7. **Assess reproducibility**: Can someone clone and run this? Check setup instructions, data dependencies, and environment assumptions.

## Output Preference

- **Repository overview**: language, size, purpose
- **Directory structure** (top-level + key subdirectories)
- **Architecture diagram** (text-based: layers and data flow)
- **Key modules and their responsibilities**
- **Entry points** (how to run, test, build)
- **Reproducibility checklist**
- **Quality observations** (strengths and risks)
- **Recommended actions** based on the user's question

## Context-Specific Modes

When the user asks about:
- **Security**: Check for secrets, input validation, auth patterns, dependency vulnerabilities.
- **Performance**: Identify hot paths, I/O patterns, caching opportunities.
- **Contribution**: Find contribution guides, issue templates, coding standards.
- **Integration**: Identify API surface, data formats, extension points.

## Quality Rules

- Always read documentation files before source code.
- Don't make claims about code you haven't read.
- When the project is large, sample strategically — acknowledge what was not inspected.
- Distinguish between "observed in the code" and "inferred from structure".
