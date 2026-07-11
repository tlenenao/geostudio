import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useItemClient } from "../../api/ItemClientProvider";
import type { CollectionSchema, DataSource } from "../../api/types";

export type FormField = {
  name: string;
  type: CollectionSchema["fields"][number]["type"];
  label: string;
  order: number;
  hidden: boolean;
  required: boolean;
  maxLength?: number;
  values?: string[];
  min?: number;
  max?: number;
  pattern?: string;
};

function fieldsFromSchema(schema: CollectionSchema): FormField[] {
  return schema.fields.map((f, i) => ({
    name: f.name,
    type: f.type,
    label: f.name,
    order: i,
    hidden: false,
    required: f.required,
    ...(f.maxLength !== undefined ? { maxLength: f.maxLength } : {}),
    ...(f.values !== undefined ? { values: f.values } : {}),
  }));
}

function FormPropsPanel({
  props,
  onChange,
  dataSources,
}: {
  props: Record<string, unknown>;
  onChange: (props: Record<string, unknown>) => void;
  dataSources: DataSource[];
}) {
  const client = useItemClient();
  const dataSourceId = String(props.dataSourceId ?? "");
  const fields = (props.fields as FormField[] | undefined) ?? [];
  const source = dataSources.find((s) => s.id === dataSourceId);
  const collectionId = source?.layer ?? "";
  const schemaQuery = useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId),
    enabled: collectionId !== "",
  });

  return (
    <div className="flex flex-col gap-2 text-sm">
      <DataSourceSelect
        value={dataSourceId}
        dataSources={dataSources.filter((s) => s.type === "features")}
        onChange={(id) => onChange({ ...props, dataSourceId: id, fields: [], geometryType: null })}
      />
      {collectionId !== "" && schemaQuery.isLoading && (
        <p className="text-xs text-[var(--gs-color-muted)]">Chargement du schéma…</p>
      )}
      {collectionId !== "" && schemaQuery.isError && (
        <p role="alert" className="text-xs text-red-600">Schéma introuvable pour « {collectionId} ».</p>
      )}
      {collectionId !== "" && schemaQuery.data && fields.length === 0 && (
        <button
          type="button"
          className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
          onClick={() =>
            onChange({
              ...props,
              fields: fieldsFromSchema(schemaQuery.data),
              geometryType: schemaQuery.data.geometry?.type ?? null,
            })
          }
        >
          Charger les champs du schéma
        </button>
      )}
    </div>
  );
}

function FormComponent() {
  return <p className="text-xs text-[var(--gs-color-muted)]">Formulaire (à suivre)</p>;
}

export function registerFormWidget(): void {
  registerWidget({
    type: "form",
    label: "Formulaire",
    defaultProps: { dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null },
    defaultSize: { w: 4, h: 6 },
    events: ["submitted", "failed"],
    actions: ["reset"],
    PropsPanel: FormPropsPanel,
    Component: FormComponent,
  });
}
