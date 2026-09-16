"""Resource integrity only: these tests neither invoke nor grade a model."""

import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def prose(text):
    return re.sub(r"(?ms)^```[^\n]*\n.*?^```[^\n]*(?:\n|$)", "", text)


def anchor(heading):
    value = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return value.replace(" ", "-")


def local_links(path):
    for target in re.findall(r"\]\(([^\s)]+)\)", prose(path.read_text(encoding="utf-8"))):
        parts = urlsplit(target)
        if parts.scheme or parts.netloc:
            continue
        destination = (path.parent / unquote(parts.path)).resolve() if parts.path else path
        if not destination.is_relative_to(ROOT):
            raise ValueError("Link leaves repository: " + target)
        yield destination, unquote(parts.fragment)


class ResourceTests(unittest.TestCase):
    def test_skill_identity_and_description(self):
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        header = re.match(r"\A---\n(.*?)\n---\n", text, re.S)
        self.assertIsNotNone(header)
        fields = dict(line.split(":", 1) for line in header.group(1).splitlines())
        self.assertEqual(fields["name"].strip(), "yandex-tone-of-voice")
        description = json.loads(fields["description"].strip())
        self.assertIsInstance(description, str)
        self.assertTrue(0 < len(description) <= 1024)
        self.assertEqual(list(ROOT.glob("SKILL.md")), [ROOT / "SKILL.md"])

    def test_runtime_links_are_complete_and_do_not_require_evaluations(self):
        files = [ROOT / "SKILL.md", *sorted((ROOT / "references").glob("*.md"))]
        allowed = set(files) | {ROOT / "LICENSE"}
        for path in files:
            for destination, fragment in local_links(path):
                with self.subTest(source=path.name, target=destination.name):
                    self.assertIn(destination, allowed)
                    self.assertTrue(destination.is_file())
                    if fragment:
                        headings = re.findall(r"(?m)^#{1,6} (.+)$", prose(destination.read_text(encoding="utf-8")))
                        self.assertIn(fragment, {anchor(h) for h in headings})

    def test_documentation_links(self):
        files = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md")), ROOT / "evals/README.md"]
        for path in files:
            for destination, fragment in local_links(path):
                with self.subTest(source=path.name, target=destination.name):
                    self.assertTrue(destination.exists())
                    if fragment:
                        headings = re.findall(r"(?m)^#{1,6} (.+)$", prose(destination.read_text(encoding="utf-8")))
                        self.assertIn(fragment, {anchor(h) for h in headings})

    def test_legacy_evaluation_shapes(self):
        suite = json.loads((ROOT / "evals/evals.json").read_text(encoding="utf-8"))
        self.assertEqual(suite["skill_name"], "yandex-tone-of-voice")
        ids = [case["id"] for case in suite["evals"]]
        self.assertTrue(ids)
        self.assertEqual(len(ids), len(set(ids)))
        for case in suite["evals"]:
            self.assertTrue(case["prompt"] and case["expected_output"] and case["expectations"])
            self.assertIsInstance(case["files"], list)
        invocation = json.loads((ROOT / "evals/invocation.json").read_text(encoding="utf-8"))
        self.assertEqual({case["should_trigger"] for case in invocation}, {True, False})
        for case in invocation:
            self.assertIsInstance(case["should_trigger"], bool)
            self.assertTrue(case["query"])

    def test_boundary_inputs_and_rubric_stay_separate(self):
        prompts = json.loads((ROOT / "evals/boundary-prompts.json").read_text(encoding="utf-8"))
        rubric = json.loads((ROOT / "evals/boundary-rubric.json").read_text(encoding="utf-8"))
        ids = [case["id"] for case in prompts]
        graded = [case["id"] for case in rubric["cases"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(graded), len(set(graded)))
        self.assertEqual(set(ids), set(graded))
        for case in prompts:
            self.assertEqual(set(case), {"id", "prompt"})
            self.assertRegex(case["id"], r"^T\d{2}$")
            self.assertTrue(case["prompt"])
        for case in rubric["cases"]:
            self.assertTrue(case["expectations"])
            self.assertTrue(all(isinstance(item, str) and item for item in case["expectations"]))
        pairs = rubric["contrast_pairs"]
        self.assertEqual(len(pairs), len({tuple(sorted(pair)) for pair in pairs}))
        for pair in pairs:
            self.assertEqual(len(pair), 2)
            self.assertEqual(len(set(pair)), 2)
            self.assertTrue(set(pair) <= set(ids))
        self.assertRegex(rubric["baseline"], r"^[0-9a-f]{40}$")
        self.assertEqual(rubric["status"], "NOT RUN")

    def test_link_helpers_preserve_real_prose(self):
        self.assertEqual(prose("Intro\n```md\n[x](missing.md)\n```\nEnd\n"), "Intro\nEnd\n")
        self.assertEqual(anchor("8. Ответственный слой"), "8-ответственный-слой")
        self.assertEqual(anchor("CTA"), "cta")


if __name__ == "__main__":
    unittest.main()
