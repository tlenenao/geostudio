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
    // REV-323 : dialogues modaux / états transitoires exclus, plus de disable par site.
    "const a = <Button onClick={() => setConfirmOpen(true)} />;",
    "const a = <Button onClick={() => setSaveDialogOpen(true)} />;",
    "const a = <Button onClick={() => setCopied(true)} />;",
    "const a = <Button onClick={() => setBusy(!busy)} />;",
    // Gestionnaire identifiant : relayé via triggerProps, ou n'ouvrant rien.
    "const go = () => save(); const a = <button onClick={go} />;",
    "const go = () => setOpen(true); const a = <button onClick={go} {...panel.triggerProps} />;",
    // Gestionnaire non résoluble (prop/import) : pas de faux positif.
    "const a = <button onClick={props.onOpen} />;",
    // Select : porte ses propres aria-*, jamais un déclencheur onClick.
    "const a = <Select onValueChange={(v) => setOpen(true)} />;",
  ],
  invalid: [
    // REV-323 : gestionnaire identifiant (fonction, const fléchée, useCallback) et IconButton.
    {
      code: "const open = () => setOpen(true); const a = <button onClick={open} />;",
      errors: [{ messageId: "missing" }],
    },
    {
      code: "function open() { setShown((s) => !s); } const a = <Button onClick={open} />;",
      errors: [{ messageId: "missing" }],
    },
    {
      code: "const open = useCallback(() => setOpen(true), []); const a = <button onClick={open} />;",
      errors: [{ messageId: "missing" }],
    },
    {
      code: "const a = <IconButton onClick={() => setExpanded(!expanded)} />;",
      errors: [{ messageId: "missing" }],
    },
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
