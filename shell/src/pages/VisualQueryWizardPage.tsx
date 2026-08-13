// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/useAuth";
import { useItemClient } from "../api/ItemClientProvider";
import { useCollectionsAdmin, usePipelineConfig } from "../api/hooks";
import type { CollectionSchema, PipelineRefreshPolicy } from "../api/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { QueryFilterBuilder } from "../builder/visualQuery/QueryFilterBuilder";
import { QueryJoinPicker } from "../builder/visualQuery/QueryJoinPicker";
import { QuerySummaryBuilder } from "../builder/visualQuery/QuerySummaryBuilder";
import { PipelineScheduleEditor } from "../builder/pipeline/PipelineScheduleEditor";
import { PipelineRunPanel } from "../builder/pipeline/PipelineRunPanel";
import { inferOutputColumns } from "../builder/visualQuery/inferSchema";
import { FilterRow, isFilterRowValueValid } from "../builder/visualQuery/compileFilter";
import { InferredSchema, JoinConfig, SummaryConfig } from "../builder/visualQuery/inferSchema";
import { VisualQueryState, compileVisualQueryToPipeline, decompilePipelineToWizardState } from "../builder/visualQuery/compilePipeline";

// Compare le schéma de sortie recompilé (déduit de l'état courant du
// formulaire) au schéma réel de la collection de sortie déjà provisionnée,
// pour bloquer une modification en mode édition qui rendrait tout run futur
// silencieusement en échec (Important 1, revue finale d'intégration SP-14o).
function outputSchemaMatches(inferred: InferredSchema, existing: CollectionSchema): boolean {
  const existingNames = new Set(existing.fields.map((f) => f.name));
  const inferredNames = new Set(inferred.columns.map((c) => c.name));
  if (existingNames.size !== inferredNames.size) return false;
  for (const name of inferredNames) if (!existingNames.has(name)) return false;
  return (existing.geometry !== null) === (inferred.geometryType !== null);
}

export function VisualQueryWizardPage({ pipelinePk, initialTitle }: { pipelinePk: string | null; initialTitle?: string }) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const client = useItemClient();
  const collectionsQuery = useCollectionsAdmin({ enabled: true });
  const existingPipelineQuery = usePipelineConfig(pipelinePk ?? "", { enabled: pipelinePk !== null });

  const [title, setTitle] = useState(initialTitle ?? "");
  const [baseCollectionId, setBaseCollectionId] = useState("");
  const [filters, setFilters] = useState<FilterRow[]>([]);
  const [join, setJoin] = useState<JoinConfig | null>(null);
  const [summary, setSummary] = useState<SummaryConfig | null>(null);
  const [refreshPolicy, setRefreshPolicy] = useState<PipelineRefreshPolicy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [createdPipelinePk, setCreatedPipelinePk] = useState<string | null>(null);
  const [createdDatasetPk, setCreatedDatasetPk] = useState<string | null>(null);
  const [unrecognizedShape, setUnrecognizedShape] = useState(false);
  const [existingOutput, setExistingOutput] = useState<{ collectionId: string; datasetItemId: string } | null>(null);
  const [titleTouched, setTitleTouched] = useState(false);

  const baseSchemaQuery = useQuery({
    queryKey: ["collection-schema", baseCollectionId],
    queryFn: () => client.getCollectionSchema(baseCollectionId),
    enabled: Boolean(baseCollectionId),
  });
  const joinedSchemaQuery = useQuery({
    queryKey: ["collection-schema", join?.collectionId],
    queryFn: () => client.getCollectionSchema(join!.collectionId),
    enabled: Boolean(join?.collectionId),
  });
  // Le Pipeline ne porte pas de titre (seul l'item dataset en a un) : en mode
  // édition, on va le chercher séparément pour pré-remplir le champ Titre.
  const existingDatasetItemQuery = useQuery({
    queryKey: ["item", existingOutput?.datasetItemId],
    queryFn: () => client.getItem(existingOutput!.datasetItemId),
    enabled: Boolean(existingOutput?.datasetItemId),
  });
  // Schéma réel de la collection de sortie déjà provisionnée (mode édition
  // seulement) — sert de référence pour détecter une incompatibilité de
  // schéma avant soumission (Important 1).
  const existingOutputSchemaQuery = useQuery({
    queryKey: ["collection-schema", existingOutput?.collectionId],
    queryFn: () => client.getCollectionSchema(existingOutput!.collectionId),
    enabled: Boolean(existingOutput?.collectionId),
  });

  useEffect(() => {
    if (pipelinePk === null || !existingPipelineQuery.data) return;
    const decompiled = decompilePipelineToWizardState(existingPipelineQuery.data);
    if (decompiled === null) { setUnrecognizedShape(true); return; }
    setBaseCollectionId(decompiled.baseCollectionId);
    setFilters(decompiled.filters);
    setJoin(decompiled.join);
    setSummary(decompiled.summary);
    setRefreshPolicy(existingPipelineQuery.data.refreshPolicy ?? null);
    setExistingOutput({ collectionId: decompiled.outputCollectionId, datasetItemId: decompiled.datasetItemId });
  }, [pipelinePk, existingPipelineQuery.data]);

  // Pré-remplit le Titre depuis l'item dataset une seule fois (la queryKey
  // ne change plus une fois existingOutput posé, donc cet effet ne se
  // redéclenche pas quand l'utilisateur modifie le titre ensuite). Gardé par
  // titleTouched : entre la résolution de existingPipelineQuery (qui affiche
  // déjà "Collection de base") et celle de existingDatasetItemQuery (second
  // aller-retour), l'utilisateur peut avoir commencé à taper un titre — ne
  // pas l'écraser silencieusement.
  useEffect(() => {
    if (existingDatasetItemQuery.data && !titleTouched) setTitle(existingDatasetItemQuery.data.title);
  }, [existingDatasetItemQuery.data, titleTouched]);

  useEffect(() => {
    if (!createdPipelinePk || !createdDatasetPk) return;
    let cancelled = false;
    async function poll() {
      while (!cancelled) {
        const runs = await client.getPipelineRuns(createdPipelinePk!);
        if (cancelled) return;
        const latest = runs[0];
        if (latest && latest.status !== "queued" && latest.status !== "running") {
          if (latest.status === "succeeded") { navigate(`/datasets/${createdDatasetPk}/edit`); return; }
          // Run terminé en échec (ou tout autre statut terminal non
          // "succeeded") : ne pas laisser l'écran "Exécution de la
          // requête…" affiché indéfiniment — revenir au formulaire avec un
          // message d'erreur explicite (Important 2).
          setError(latest.error ?? "L'exécution du pipeline a échoué.");
          setCreatedPipelinePk(null);
          setCreatedDatasetPk(null);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
    }
    poll();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [createdPipelinePk, createdDatasetPk]);

  if (pipelinePk !== null && unrecognizedShape) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Cette requête a été modifiée dans l'éditeur avancé et ne peut plus être ouverte dans
        l'assistant. <a className="underline" href={`/pipelines/${pipelinePk}/edit`}>Ouvrir dans l'éditeur avancé</a>.
      </p>
    );
  }

  const baseSchema: CollectionSchema | undefined = baseSchemaQuery.data;

  // Calculé une fois pour être réutilisé à la fois par le garde-fou
  // ci-dessous et par la branche création de handleCreate (évite de
  // dupliquer l'appel à inferOutputColumns).
  const inferredOutput: InferredSchema | null = baseSchema
    ? inferOutputColumns(baseSchema, join, joinedSchemaQuery.data ?? null, summary)
    : null;
  // Incompatibilité de schéma de sortie, mode édition seulement (Important
  // 1) : bloque la soumission tant que le schéma recompilé ne correspond
  // plus à la collection de sortie déjà provisionnée.
  const outputSchemaMismatch =
    pipelinePk !== null && inferredOutput !== null && existingOutputSchemaQuery.data !== undefined
    && !outputSchemaMatches(inferredOutput, existingOutputSchemaQuery.data);

  async function handleCreate() {
    if (!baseSchema) return;
    setError(null);
    setSubmitting(true);
    try {
      const state: VisualQueryState = { title, baseCollectionId, filters, join, summary, refreshPolicy };
      let outputCollectionId: string;
      let datasetPk: string;
      let pipelinePkToRun: string;

      if (pipelinePk !== null && existingOutput) {
        outputCollectionId = existingOutput.collectionId;
        datasetPk = existingOutput.datasetItemId;
        pipelinePkToRun = pipelinePk;
        const pipeline = compileVisualQueryToPipeline(
          state, baseSchema, joinedSchemaQuery.data ?? null, outputCollectionId, datasetPk,
        );
        await client.savePipelineConfig(pipelinePk, pipeline);
        await client.updateItem(datasetPk, { title });
      } else {
        // baseSchema est garanti défini ici (contrôle en tête de fonction),
        // donc inferredOutput (calculé à partir de baseSchema) l'est aussi.
        const inferred = inferredOutput!;
        const { id: newCollectionId } = await client.createEmptyCollection({
          title: `${title} (données)`,
          columns: inferred.columns.map((c) => ({ name: c.name, sqlType: c.sqlType })),
          geometryType: inferred.geometryType, srid: inferred.srid,
        });
        outputCollectionId = newCollectionId;
        const datasetItem = await client.createDatasetItem({
          title, owner: username ?? "", source: "collection", collectionId: outputCollectionId,
        });
        datasetPk = datasetItem.pk;
        const pipeline = compileVisualQueryToPipeline(
          state, baseSchema, joinedSchemaQuery.data ?? null, outputCollectionId, datasetPk,
        );
        const pipelineItem = await client.createPipelineItem({
          title: `Requête — ${title}`, owner: username ?? "", pipeline,
        });
        pipelinePkToRun = pipelineItem.pk;
        await client.saveDatasetConfig(datasetPk, {
          source: "collection", collectionId: outputCollectionId, columns: {},
          sourcePipelineId: pipelinePkToRun,
        });
      }

      await client.runPipeline(pipelinePkToRun);
      setCreatedPipelinePk(pipelinePkToRun);
      setCreatedDatasetPk(datasetPk);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Échec de l'enregistrement.");
    } finally {
      setSubmitting(false);
    }
  }

  const filtersValid = !baseSchema || filters.every((row) => isFilterRowValueValid(row, baseSchema));
  const joinValid = !join || Boolean(join.collectionId && join.on);
  const summaryValid = !summary || summary.groupBy.length > 0 || summary.metrics.length > 0;

  if (createdPipelinePk && createdDatasetPk) {
    return (
      <div className="flex flex-col gap-2 p-4">
        <p>Exécution de la requête…</p>
        <PipelineRunPanel pipelineId={createdPipelinePk} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="text-xl font-semibold">
        {pipelinePk !== null ? "Modifier la requête" : "Nouvelle requête visuelle"}
      </h2>
      <label className="flex flex-col gap-1 text-sm">
        Titre
        <Input aria-label="Titre" value={title} onChange={(e) => { setTitle(e.target.value); setTitleTouched(true); }} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Collection de base
        <select
          aria-label="Collection de base"
          className="h-9 rounded-md border border-slate-300 px-3 text-sm"
          value={baseCollectionId}
          onChange={(e) => {
            // Important 3 : un changement direct de collection de base
            // invalide filtres/jointure/résumé (colonnes qui n'existent
            // plus forcément dans la nouvelle collection) — réinitialiser
            // pour éviter un état validé à tort qui échouerait à
            // l'exécution. Le useEffect de décompilation (chargement d'une
            // requête existante) pose ces mêmes champs ensemble et n'a pas
            // besoin de ce garde : ce n'est pas une interaction utilisateur.
            setBaseCollectionId(e.target.value);
            setFilters([]);
            setJoin(null);
            setSummary(null);
          }}
        >
          <option value="">Choisir…</option>
          {(collectionsQuery.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
      </label>
      {baseSchema && (
        <>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Filtrer</p>
            <QueryFilterBuilder schema={baseSchema} rows={filters} onChange={setFilters} />
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Joindre</p>
            {join ? (
              <div className="flex flex-col gap-2">
                <QueryJoinPicker
                  baseSchema={baseSchema} joinedSchema={joinedSchemaQuery.data ?? null}
                  collections={collectionsQuery.data ?? []} value={join} onChange={setJoin}
                />
                <Button type="button" size="sm" variant="outline" onClick={() => setJoin(null)}>
                  Supprimer la jointure
                </Button>
              </div>
            ) : (
              <Button type="button" size="sm" variant="outline" onClick={() => setJoin({ collectionId: "", on: "", how: "inner" })}>
                Ajouter une jointure
              </Button>
            )}
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Résumer</p>
            {summary ? (
              <div className="flex flex-col gap-2">
                <QuerySummaryBuilder schema={baseSchema} value={summary} onChange={setSummary} />
                <Button type="button" size="sm" variant="outline" onClick={() => setSummary(null)}>
                  Supprimer le résumé
                </Button>
              </div>
            ) : (
              <Button type="button" size="sm" variant="outline" onClick={() => setSummary({ groupBy: [], metrics: [] })}>
                Ajouter un résumé
              </Button>
            )}
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Planifier</p>
            <PipelineScheduleEditor value={refreshPolicy} onChange={setRefreshPolicy} />
          </div>
        </>
      )}
      {pipelinePk !== null && outputSchemaMismatch && (
        <p role="alert" className="text-sm text-red-600">
          La structure de sortie a changé (colonnes ou géométrie) : cette
          modification ne peut pas être enregistrée sur la requête existante.
          Créez une nouvelle requête à la place.
        </p>
      )}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <Button
        size="sm" className="w-fit"
        disabled={
          submitting || !title.trim() || !baseCollectionId || !filtersValid || !joinValid || !summaryValid
          || (pipelinePk !== null && !existingOutput) || outputSchemaMismatch
        }
        onClick={handleCreate}
      >
        {pipelinePk !== null ? "Mettre à jour" : "Créer"}
      </Button>
    </div>
  );
}
