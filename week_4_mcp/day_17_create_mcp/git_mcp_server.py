#!/usr/bin/env python3
"""
Собственный MCP-сервер вокруг Git CLI.

Запускается локально через stdio-транспорт (FastMCP сам поднимает
stdin/stdout сервер при запуске скрипта). Регистрирует набор инструментов
для чтения состояния git-репозитория: status, log, diff, список веток,
показ конкретного коммита.

Запуск напрямую (для ручной проверки протокола не предполагается,
сервер общается по stdio с клиентом, см. git_mcp_client.py):
    python3 git_mcp_server.py
"""

import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("git-mcp-server")


def _run_git(repo_path: str, args: list[str]) -> str:
    """Выполняет `git <args>` в указанном репозитории и возвращает stdout/stderr."""
    result = subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return f"git error (code {result.returncode}): {result.stderr.strip()}"
    return result.stdout.strip() or "(пустой вывод)"


@mcp.tool()
def git_status(repo_path: str = ".") -> str:
    """Показывает статус рабочей директории git-репозитория (git status --short --branch).

    Args:
        repo_path: путь к git-репозиторию на диске.
    """
    return _run_git(repo_path, ["status", "--short", "--branch"])


@mcp.tool()
def git_log(repo_path: str = ".", max_count: int = 10) -> str:
    """Показывает последние коммиты репозитория (git log --oneline).

    Args:
        repo_path: путь к git-репозиторию на диске.
        max_count: сколько последних коммитов вернуть (по умолчанию 10).
    """
    return _run_git(repo_path, ["log", f"-n{max_count}", "--oneline", "--decorate"])


@mcp.tool()
def git_diff(repo_path: str = ".", staged: bool = False) -> str:
    """Показывает diff незакоммиченных изменений.

    Args:
        repo_path: путь к git-репозиторию на диске.
        staged: если True — diff только для застейдженных изменений (git diff --staged),
            иначе diff рабочей директории (git diff).
    """
    args = ["diff", "--staged"] if staged else ["diff"]
    return _run_git(repo_path, args)


@mcp.tool()
def git_branch_list(repo_path: str = ".") -> str:
    """Возвращает список веток репозитория с указанием текущей (git branch).

    Args:
        repo_path: путь к git-репозиторию на диске.
    """
    return _run_git(repo_path, ["branch", "--all"])


@mcp.tool()
def git_current_branch(repo_path: str = ".") -> str:
    """Возвращает имя текущей ветки (git rev-parse --abbrev-ref HEAD).

    Args:
        repo_path: путь к git-репозиторию на диске.
    """
    return _run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])


@mcp.tool()
def git_ls_files(repo_path: str = ".", pattern: str = "") -> str:
    """Список файлов, отслеживаемых git (git ls-files), опционально по glob-паттерну.

    Args:
        repo_path: путь к git-репозиторию на диске.
        pattern: необязательный pathspec/glob для фильтрации (например 'docs/*.md').
    """
    args = ["ls-files"]
    if pattern:
        args.append(pattern)
    return _run_git(repo_path, args)


@mcp.tool()
def git_show_commit(repo_path: str = ".", commit_hash: str = "HEAD") -> str:
    """Показывает сообщение и diff конкретного коммита (git show).

    Args:
        repo_path: путь к git-репозиторию на диске.
        commit_hash: хеш или ссылка на коммит (по умолчанию HEAD).
    """
    return _run_git(repo_path, ["show", commit_hash])


if __name__ == "__main__":
    mcp.run(transport="stdio")
