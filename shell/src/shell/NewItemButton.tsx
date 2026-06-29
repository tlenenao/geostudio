import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateItem } from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";

export function NewItemButton() {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"app" | "dashboard">("app");
  const [title, setTitle] = useState("");
  const { username } = useAuth();
  const navigate = useNavigate();
  const create = useCreateItem();

  function close() {
    setOpen(false);
    setTitle("");
    setKind("app");
    create.reset();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    try {
      const item = await create.mutateAsync({ kind, title: clean, owner: username ?? "" });
      close();
      navigate(`/items/${item.pk}`);
    } catch {
      // error surfaced via create.isError
    }
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Nouveau
      </Button>
      <Dialog open={open} onClose={close} title="Nouvel élément">
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Type
            <select
              aria-label="Type"
              className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
              value={kind}
              onChange={(e) => setKind(e.target.value as "app" | "dashboard")}
            >
              <option value="app">App</option>
              <option value="dashboard">Dashboard</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Titre
            <Input
              aria-label="Titre"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          {create.isError && (
            <p role="alert" className="text-sm text-red-600">
              Échec de la création.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Annuler
            </Button>
            <Button type="submit" size="sm" disabled={create.isPending}>
              Créer
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
