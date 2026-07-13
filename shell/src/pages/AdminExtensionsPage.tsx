import { useAllExtensions, useMe, useSetExtensionEnabled } from "../api/hooks";

export function AdminExtensionsPage() {
  const meQuery = useMe();
  const extensionsQuery = useAllExtensions({ enabled: meQuery.data?.isAdmin === true });
  const setEnabled = useSetExtensionEnabled();

  if (meQuery.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (meQuery.data?.isAdmin !== true) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Accès réservé aux administrateurs.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-lg font-bold">Extensions</h1>
      {extensionsQuery.isLoading && <p role="status">Chargement…</p>}
      {extensionsQuery.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec du chargement des extensions.
        </p>
      )}
      {extensionsQuery.data && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="py-2">Étiquette</th>
              <th className="py-2">Balise</th>
              <th className="py-2">Module</th>
              <th className="py-2">Actif</th>
            </tr>
          </thead>
          <tbody>
            {extensionsQuery.data.map((ext) => (
              <tr key={ext.type} className="border-b border-slate-100">
                <td className="py-2">{ext.label}</td>
                <td className="py-2">{ext.tag}</td>
                <td className="py-2 text-xs text-slate-500">{ext.moduleUrl}</td>
                <td className="py-2">
                  <input
                    type="checkbox"
                    aria-label={`Actif : ${ext.label}`}
                    checked={ext.enabled}
                    disabled={setEnabled.isPending}
                    onChange={(e) => setEnabled.mutate({ id: ext.type, enabled: e.target.checked })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
