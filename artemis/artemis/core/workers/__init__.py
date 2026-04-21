"""Artemis worker agents — domain specialists."""
from artemis.core.workers.body_agent import body_agent
from artemis.core.workers.home_agent import home_agent
from artemis.core.workers.mind_agent import mind_agent
from artemis.core.workers.travel_agent import travel_agent
from artemis.core.workers.work_agent import work_agent

WORKER_REGISTRY: dict = {
    "body": body_agent,
    "mind": mind_agent,
    "work": work_agent,
    "home": home_agent,
    "travel": travel_agent,
}
