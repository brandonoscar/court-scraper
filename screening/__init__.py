"""Screening layer for civil money judgments.

A thin, isolated module that reads the court-scraper's *output* and ranks which
money judgments are worth pursuing under the "collectible debtor, dormant paper"
thesis. It never touches the scraper's fetching internals, and every
qualification decision comes from explicit hard-coded rules (see rules.py),
never from a model.
"""
