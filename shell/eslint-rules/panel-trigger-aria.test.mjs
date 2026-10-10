// SPDX-License-Identifier: Apache-2.0
import { RuleTester } from "eslint";
import { describe, it } from "vitest";
import rule from "./panel-trigger-aria.mjs";

RuleTester.describe = describe;
RuleTester.it = it;
RuleTester.itOnly = it.only;

const tester = new RuleTester({
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: "module",
    parserOptions: { ecmaFeatures: { jsx: true } },
  },
});

tester.run("panel-trigger-aria", rule, {
  valid: [
    'const a = <button onClick={() => setOpen(true)} aria-expanded={open} aria-controls="p" />;',
    "const a = <Button onClick={() => setOpen((o) => !o)} {...panel.triggerProps} />;",
    "const a = <Button onClick={() => setOpen(true)} {...triggerProps} />;",
    "const a = <button onClick={() => setOpen(false)} />;",
    'const a = <button onClick={() => setName("x")} />;',
    "const a = <button onClick={() => save()} />;",
  ],
  invalid: [
    {
      code: "const a = <button onClick={() => setOpen(true)} />;",
      errors: [{ messageId: "missing" }],
    },
    {
      code: "const a = <Button onClick={() => setOpen(!open)} />;",
      errors: [{ messageId: "missing" }],
    },
    {
      code: "const a = <button onClick={() => setOpen((o) => !o)} />;",
      errors: [{ messageId: "missing" }],
    },
    {
      code: "const a = <button onClick={() => menu.toggle()} />;",
      errors: [{ messageId: "missing" }],
    },
    {
      code: "const a = <button onClick={() => (open ? close() : setOpen(true))} />;",
      errors: [{ messageId: "missing" }],
    },
    {
      code: "const a = <button onClick={() => setOpen(true)} aria-expanded={open} />;",
      errors: [{ messageId: "missing" }],
    },
  ],
});
