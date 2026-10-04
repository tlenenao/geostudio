/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { bug } from "../_fixtures/verify";
import { test, expect } from "@playwright/test";
import {
  HOOK,
  alertConfig,
  apiFor,
  deferEvaluation,
  getAlertSeed,
  mkRule,
  newEvaluation,
  psql,
  recvLog,
  runnerEvaluate,
  startHarness,
  stopHarness,
  waitEvaluation,
  type Api,
} from "./helpers";
import { stamp } from "../_fixtures/env";

// Livraison RÉELLE des notifications d'alerte : webhook reçu par un récepteur jetable sur un
// sous-réseau routable (la garde d'egress refuse toute cible interne), e-mail reçu par un SMTP
// jetable joint par le vrai worker. Conteneur et réseau créés puis supprimés par cette spec.
test.setTimeout(180_000);

const tag = stamp("j09b");
let creator: Api;
let admin: Api;
let datasetId: string;
let smtpName: string;
let sweepRuleId: string;
const SWEEP_TITLE = `${tag}-sweep-mail`;

const notifyAudit = (itemId: string) =>
  psql(
    `SELECT payload::text FROM audit_log WHERE action='alert.notify' AND object_id='${itemId}' ORDER BY created_at`,
  )
    .trim()
    .split("\n")
    .filter(Boolean)
    .map((l) => JSON.parse(l));

const hooksFor = (title: string) => recvLog("http").filter((h) => h.body.includes(`"${title}"`));

async function smtpSecret(
  api: Api,
  name: string,
  over: Record<string, unknown> = {},
): Promise<number> {
  const r = await api.send("POST", "/v1/secrets", {
    name,
    payload: {
      kind: "smtp",
      host: "audit-j09b-recv",
      // Règle 3c9f5f0d : useTls=false refusé hors localhost. On cible donc le port STARTTLS (2526) ;
      // MAIS le certificat du récepteur (recv.py) est auto-signé, non vérifiable par le cœur
      // (add915de) : la livraison échouera tant que recv.py n'a pas un cert signé par une CA de confiance.
      // À corriger côté récepteur, jamais en affaiblissant le cœur.
      port: 2526,
      username: "alerts",
      password: "s3cret-pw",
      useTls: true,
      fromAddress: "alerts@audit.test",
      ...over,
    },
  });
  return r.status;
}

test.beforeAll(async () => {
  startHarness();
  const s = await getAlertSeed();
  creator = s.creator;
  datasetId = s.datasetId;
  admin = await apiFor("admin");
  smtpName = `${tag}-smtp`;
  expect(await smtpSecret(admin, smtpName)).toBe(201);
  // Règle à balayage périodique réel (*/5) : le worker évalue puis envoie l'e-mail sans aide.
  sweepRuleId = await mkRule(creator, datasetId, SWEEP_TITLE, {
    refreshPolicy: { enabled: true, cron: "*/5 * * * *" },
    channels: [{ kind: "email", to: "ops@audit.test", smtpSecretName: smtpName }],
  });
});

test.afterAll(() => {
  stopHarness();
});

test("webhook : firing livre un JSON complet (audité), pas de renotification sans transition, 'ok' au retour à la normale", async () => {
  const title = `${tag}-hook-firing`;
  const id = await mkRule(creator, datasetId, title, {
    channels: [{ kind: "webhook", url: `${HOOK}/hook` }],
  });
  const evalId = await newEvaluation(creator, id);
  runnerEvaluate(evalId);
  const ev = await waitEvaluation(creator, id, evalId);
  expect(ev.state).toBe("firing");
  const got = hooksFor(title);
  expect(got).toHaveLength(1);
  const body = JSON.parse(got[0].body);
  expect(body).toMatchObject({ ruleName: title, state: "firing", value: 3 });
  expect(body.message).toContain("value=3");
  expect(got[0].headers["Content-Type"]).toBe("application/json");
  expect(notifyAudit(id)).toEqual([
    { channel: "webhook", state: "firing", success: true, error: null },
  ]);
  // 2e évaluation, même état : aucune renotification
  const e2 = await newEvaluation(creator, id);
  runnerEvaluate(e2);
  expect((await waitEvaluation(creator, id, e2)).state).toBe("firing");
  expect(hooksFor(title)).toHaveLength(1);
  // la condition cesse d'être vraie : transition vers ok, notifiée
  const cfg = await creator.get(`/v1/configs/by-item/${id}`);
  cfg.body.config.alert.condition.expr = "value > 99";
  expect((await creator.send("PUT", `/v1/configs/by-item/${id}`, cfg.body.config)).status).toBe(
    200,
  );
  const e3 = await newEvaluation(creator, id);
  runnerEvaluate(e3);
  expect((await waitEvaluation(creator, id, e3)).state).toBe("ok");
  expect(hooksFor(title).map((h) => JSON.parse(h.body).state)).toEqual(["firing", "ok"]);
});

// Finding j09b-003 : aucun secret partagé ni signature sur le webhook, le récepteur ne peut pas
// authentifier l'émetteur.
test("j09b-003 : le webhook porte une signature vérifiable (en-tête HMAC)", async () => {
  const title = `${tag}-hook-sign`;
  const secretName = `${tag}-sign-key`;
  expect(
    (
      await admin.send("POST", "/v1/secrets", {
        name: secretName,
        payload: { kind: "bearer_token", token: "signing-key" },
      })
    ).status,
  ).toBe(201);
  const id = await mkRule(creator, datasetId, title, {
    channels: [{ kind: "webhook", url: `${HOOK}/hook`, signingSecretName: secretName }],
  });
  const evalId = await newEvaluation(creator, id);
  runnerEvaluate(evalId);
  await waitEvaluation(creator, id, evalId);
  const hook = hooksFor(title)[0];
  const sig = Object.entries(hook.headers).find(
    ([h]) => h.toLowerCase() === "x-geostudio-signature",
  )?.[1] as string;
  const { createHmac } = await import("node:crypto");
  expect(sig).toBe(`sha256=${createHmac("sha256", "signing-key").update(hook.body).digest("hex")}`);
});

// Finding j09b-004 : une livraison échouée (cible 5xx) n'est jamais rejouée : la transition a
// été « consommée » et les évaluations suivantes (même état) ne renotifient pas.
test("j09b-004 : une notification webhook échouée est rejouée à l'évaluation suivante", async () => {
  const title = `${tag}-hook-fail`;
  const id = await mkRule(creator, datasetId, title, {
    channels: [{ kind: "webhook", url: `${HOOK}/fail` }],
  });
  const e1 = await newEvaluation(creator, id);
  runnerEvaluate(e1);
  await waitEvaluation(creator, id, e1);
  const audit1 = notifyAudit(id);
  expect(audit1[0].success).toBe(false);
  expect(audit1[0].error).toContain("500");
  const e2 = await newEvaluation(creator, id);
  runnerEvaluate(e2);
  await waitEvaluation(creator, id, e2);
  // Attendu : une seconde tentative ; constaté : aucune ligne alert.notify de plus.
  expect(hooksFor(title).length).toBeGreaterThan(1);
});

test("webhook : une redirection vers 169.254.169.254 est bloquée sur le saut ; une cible muette est abandonnée après 10 s", async () => {
  const redirId = await mkRule(creator, datasetId, `${tag}-hook-redir`, {
    channels: [{ kind: "webhook", url: `${HOOK}/redir` }],
  });
  const e = await newEvaluation(creator, redirId);
  runnerEvaluate(e);
  expect((await waitEvaluation(creator, redirId, e)).state).toBe("firing");
  const a = notifyAudit(redirId);
  expect(a[0].success).toBe(false);
  expect(a[0].error).toMatch(/egress blocked/);

  const slowId = await mkRule(creator, datasetId, `${tag}-hook-slow`, {
    channels: [{ kind: "webhook", url: `${HOOK}/slow` }],
  });
  const e2 = await newEvaluation(creator, slowId);
  const t0 = Date.now();
  runnerEvaluate(e2);
  const took = Date.now() - t0;
  expect((await waitEvaluation(creator, slowId, e2)).state).toBe("firing");
  const b = notifyAudit(slowId);
  expect(b[0]).toMatchObject({ success: false });
  expect(b[0].error).toMatch(/timed out|Read timed out/i);
  expect(took).toBeLessThan(25_000);
});

// Finding j09b-002 : le service `worker` n'a pas CORE_SECRETS_MASTER_KEY (docker-compose.yml ne la
// passe qu'au cœur) : le secret SMTP ne peut pas être déchiffré, aucun e-mail d'alerte n'est livré.
bug(
  "j09b-002 : le worker réel livre l'e-mail d'une alerte (secret SMTP déchiffrable)",
  async () => {
    const title = `${tag}-mail-worker`;
    const id = await mkRule(creator, datasetId, title, {
      channels: [{ kind: "email", to: "ops@audit.test", smtpSecretName: smtpName }],
    });
    const e = await newEvaluation(creator, id);
    deferEvaluation(e);
    await waitEvaluation(creator, id, e);
    expect(recvLog("smtp").filter((m) => m.data.includes(title))).toHaveLength(1);
  },
);

test("e-mail : livré au SMTP authentifié (expéditeur, destinataire, sujet, corps) ; identifiants refusés -> échec audité sans fuite du mot de passe", async () => {
  const title = `${tag}-mail-now`;
  const id = await mkRule(creator, datasetId, title, {
    channels: [{ kind: "email", to: "ops@audit.test", smtpSecretName: smtpName }],
  });
  const e = await newEvaluation(creator, id);
  runnerEvaluate(e);
  expect((await waitEvaluation(creator, id, e)).state).toBe("firing");
  const mails = recvLog("smtp").filter((m) => m.data.includes(title));
  expect(mails).toHaveLength(1);
  expect(mails[0]).toMatchObject({ user: "alerts", pass: "s3cret-pw", tls: false });
  expect(mails[0].from).toContain("alerts@audit.test");
  expect(mails[0].rcpt[0]).toContain("ops@audit.test");
  expect(mails[0].data).toContain(`Subject: [GeoStudio] ${title}: firing`);
  expect(mails[0].data).toContain("value=3");
  expect(notifyAudit(id)[0]).toMatchObject({ channel: "email", success: true });

  const name = `${tag}-smtp-bad`;
  expect(await smtpSecret(admin, name, { password: "wrong" })).toBe(201);
  const badId = await mkRule(creator, datasetId, `${tag}-mail-bad`, {
    channels: [{ kind: "email", to: "ops@audit.test", smtpSecretName: name }],
  });
  const eb = await newEvaluation(creator, badId);
  runnerEvaluate(eb);
  expect((await waitEvaluation(creator, badId, eb)).state).toBe("firing");
  const bad = notifyAudit(badId)[0];
  expect(bad.success).toBe(false);
  expect(bad.error).toMatch(/email delivery failed.*535/);
  expect(bad.error).not.toContain("wrong");
});

// Finding j09b-005 : smtp.starttls() sans contexte ne vérifie ni la chaîne ni le nom d'hôte.
bug("j09b-005 : STARTTLS refuse un certificat auto-signé au mauvais nom d'hôte", async () => {
  const name = `${tag}-smtp-tls`;
  expect(await smtpSecret(admin, name, { port: 2526, useTls: true })).toBe(201);
  const title = `${tag}-mail-tls`;
  const id = await mkRule(creator, datasetId, title, {
    channels: [{ kind: "email", to: "ops@audit.test", smtpSecretName: name }],
  });
  const e = await newEvaluation(creator, id);
  runnerEvaluate(e);
  await waitEvaluation(creator, id, e);
  const delivered = recvLog("smtp").filter((m) => m.data.includes(title) && m.tls);
  expect(delivered).toHaveLength(0);
});

// Finding j09b-006 : le secret SMTP est résolu par nom dans le tenant, sans contrôle de
// propriété ni de privilège : un Créateur sans droit sur le coffre envoie des e-mails avec le
// compte SMTP de l'administrateur, à n'importe quel destinataire.
test("j09b-006 : un Créateur ne peut pas utiliser le secret SMTP d'un autre pour envoyer", async () => {
  const title = `${tag}-mail-relay`;
  const id = await mkRule(creator, datasetId, title, {
    channels: [{ kind: "email", to: "victime@autre-domaine.test", smtpSecretName: smtpName }],
    messageTemplate: "Hameçonnage : {ruleName}",
  });
  const e = await newEvaluation(creator, id);
  runnerEvaluate(e);
  await waitEvaluation(creator, id, e);
  const sent = recvLog("smtp").filter((m) => m.rcpt.join().includes("victime@autre-domaine.test"));
  expect(sent).toHaveLength(0);
});

test("balayage périodique réel : le worker évalue seul la règle planifiée (firing) sans intervention", async () => {
  test.setTimeout(480_000);
  const deadline = Date.now() + 420_000;
  let ev: any;
  while (Date.now() < deadline) {
    const list = await creator.get(`/v1/alerts/${sweepRuleId}/evaluations`);
    ev = (list.body as any[]).find((x) => x.state !== "pending");
    if (ev) break;
    await new Promise((r) => setTimeout(r, 10_000));
  }
  expect(ev?.state).toBe("firing");
  // aucune évaluation manuelle n'a été demandée pour cette règle : seul le balayage */5 a pu la créer
  expect(alertConfig(datasetId).alert.refreshPolicy.enabled).toBe(false);
  const a = notifyAudit(sweepRuleId);
  expect(a).toHaveLength(1);
});
