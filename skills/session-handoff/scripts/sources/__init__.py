"""Source adapters. Every non-underscore module here is discovered automatically.

A source module must define: NAME, LABEL, roots(), owns(path), sessions(include_all),
session_for_path(path), messages(path). See references/adapting.md ("Adding a source").
"""
