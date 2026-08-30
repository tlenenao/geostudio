// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { useMe } from "../api/hooks";
import {
  Avatar,
  Badge,
  Banner,
  Breadcrumb,
  Button,
  Checkbox,
  Chip,
  ColorField,
  Combobox,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  Field,
  Gate,
  IconButton,
  Input,
  Kbd,
  Menu,
  NumberField,
  Panel,
  Popover,
  Progress,
  Radio,
  Section,
  Segmented,
  Select,
  Skeleton,
  Slider,
  Spinner,
  Splitter,
  Switch,
  Table,
  Tabs,
  Textarea,
  Toast,
  Toolbar,
  Tooltip,
  Tree,
} from "../ui/kit";

const WIDTHS = [390, 768, 1280];

function GalleryContent() {
  const [checked, setChecked] = useState(false);
  const [radioValue, setRadioValue] = useState("lecteur");
  const [switchOn, setSwitchOn] = useState(false);
  const [sliderValue, setSliderValue] = useState([50]);
  const [segmentedValue, setSegmentedValue] = useState("quantile");
  const [color, setColor] = useState("#0b6e77");
  const [number, setNumber] = useState(5);
  const [selectValue, setSelectValue] = useState("a");
  const [comboValue, setComboValue] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toastOpen, setToastOpen] = useState(false);

  return (
    <div className="flex flex-col gap-6 p-4">
      <Field label="Titre" htmlFor="gallery-input">
        <Input id="gallery-input" defaultValue="" />
      </Field>
      <Field label="Description" htmlFor="gallery-textarea">
        <Textarea id="gallery-textarea" defaultValue="" />
      </Field>
      <Input disabled placeholder="Désactivé" aria-label="Champ désactivé" />
      <Checkbox aria-label="Case à cocher" checked={checked} onCheckedChange={setChecked} />
      <Radio.Group aria-label="Rôle" value={radioValue} onValueChange={setRadioValue}>
        <Radio.Item value="lecteur">Lecteur</Radio.Item>
        <Radio.Item value="editeur">Éditeur</Radio.Item>
      </Radio.Group>
      <Switch aria-label="Activer" checked={switchOn} onCheckedChange={setSwitchOn} />
      <Slider aria-label="Opacité" value={sliderValue} onValueChange={setSliderValue} />
      <Segmented
        aria-label="Méthode"
        value={segmentedValue}
        onValueChange={setSegmentedValue}
        options={[
          { value: "quantile", label: "Quantile" },
          { value: "jenks", label: "Jenks" },
        ]}
      />
      <ColorField aria-label="Couleur d'accent" value={color} onValueChange={setColor} />
      <NumberField aria-label="Zoom" value={number} onValueChange={setNumber} />
      <Select
        aria-label="Format"
        value={selectValue}
        onValueChange={setSelectValue}
        options={[
          { value: "a", label: "Option A" },
          { value: "b", label: "Option B" },
        ]}
      />
      <Combobox
        aria-label="Collection"
        value={comboValue}
        onValueChange={setComboValue}
        options={[
          { value: "a", label: "Alpha" },
          { value: "b", label: "Beta" },
        ]}
      />
      <Tabs
        defaultValue="info"
        tabs={[
          { value: "info", label: "Informations", content: <p>Contenu</p> },
          { value: "perms", label: "Permissions", content: <p>Contenu</p> },
        ]}
      />
      <Tree
        nodes={[{ id: "a", label: "Cartes", children: [{ id: "a-1", label: "Carte topo" }] }]}
      />
      <Table>
        <Table.Head columns={["Nom", "Type"]} />
        <tbody>
          <Table.Row>
            <Table.Cell>Carte topo</Table.Cell>
            <Table.Cell>map</Table.Cell>
          </Table.Row>
        </tbody>
      </Table>
      <DataTable
        columns={[{ key: "name", label: "Nom", render: (r: { name: string }) => r.name }]}
        rows={[{ name: "Carte topo" }]}
        getRowId={(r) => r.name}
      />
      <Panel>
        <Section title="Section">
          <p className="text-sm text-ink">Contenu de section</p>
        </Section>
      </Panel>
      <Breadcrumb items={[{ label: "Catalogue", href: "/" }, { label: "Carte topo" }]} />
      <Toolbar.Root aria-label="Actions">
        <Toolbar.Button onClick={() => {}}>Mesurer</Toolbar.Button>
        <Toolbar.Separator />
        <Toolbar.Button onClick={() => {}} disabled>
          Croquis
        </Toolbar.Button>
      </Toolbar.Root>
      <div className="h-32">
        <Splitter first={<div>Gauche</div>} second={<div>Droite</div>} />
      </div>
      <Popover trigger={<Button variant="outline">Ouvrir un popover</Button>}>
        Contenu du popover
      </Popover>
      <Menu
        trigger={<Button variant="outline">Menu</Button>}
        items={[
          { label: "Modifier", onSelect: () => {} },
          { label: "Supprimer", onSelect: () => {}, danger: true },
        ]}
      />
      <Tooltip content="Aide contextuelle">
        <IconButton icon={<span>?</span>} aria-label="Aide" size="sm" />
      </Tooltip>
      <Button onClick={() => setConfirmOpen(true)}>Ouvrir ConfirmDialog</Button>
      <ConfirmDialog
        open={confirmOpen}
        title="Supprimer"
        message="Confirmer la suppression ?"
        confirmLabel="Supprimer"
        onConfirm={() => setConfirmOpen(false)}
        onCancel={() => setConfirmOpen(false)}
      />
      <Button onClick={() => setDrawerOpen(true)}>Ouvrir Drawer</Button>
      <Drawer open={drawerOpen} onOpenChange={setDrawerOpen} title="Explorateur">
        <p className="text-sm text-ink">Contenu du panneau</p>
      </Drawer>
      <Button onClick={() => setToastOpen(true)}>Déclencher un toast</Button>
      <Toast open={toastOpen} onOpenChange={setToastOpen} title="Enregistré" description="OK" />
      <Badge variant="ok">Publié</Badge>
      <Chip onRemove={() => {}}>type: map</Chip>
      <Skeleton className="h-4 w-32" />
      <Spinner aria-label="Chargement" />
      <Progress aria-label="Import" value={40} />
      <EmptyState title="Aucun résultat" description="Essayez un autre filtre." />
      <Banner variant="warn">Bannière d'avertissement</Banner>
      <Avatar alt="Tanguy" fallback="TL" />
      <Kbd>⌘K</Kbd>
      <Gate
        on={{ permissions: { read: true, write: false, delete: false, share: false } }}
        can="write"
      >
        <Button>Action verrouillée si non éditeur</Button>
      </Gate>
    </div>
  );
}

export function KitGalleryPage() {
  const meQuery = useMe();
  const [theme, setTheme] = useState<"light" | "dark" | undefined>(undefined);

  if (meQuery.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (meQuery.data?.isAdmin !== true) {
    return (
      <p role="alert" className="text-sm text-danger">
        Accès réservé aux administrateurs.
      </p>
    );
  }

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
  };

  return (
    // Fournisseurs Radix locaux : cette page est atteignable directement (route
    // /internal/kit-gallery) et rend Tooltip/Toast au montage — ces deux
    // primitives lèvent hors d'un Provider (vérifié : le montage plante avec
    // "must be used within TooltipProvider"/ToastProvider sans ce wrapper),
    // contrairement au reste du kit qui ne l'exige qu'à l'ouverture. App.tsx
    // fournit déjà les siens à la racine ; l'imbrication est sans danger.
    <ToastPrimitive.Provider>
      <TooltipPrimitive.Provider>
        <div className="flex flex-col gap-4 p-4">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-bold text-ink">Galerie de primitives</h1>
            <Button onClick={toggleTheme}>
              {theme === "dark" ? "Ambiance claire" : "Ambiance sombre"}
            </Button>
          </div>
          <div className="flex flex-col gap-4">
            {WIDTHS.map((width) => (
              <div key={width} className="overflow-x-auto">
                <p className="mb-2 text-xs text-ink-3">{width}px</p>
                <div
                  style={{ width, minWidth: width }}
                  className="border border-dashed border-rule"
                >
                  <GalleryContent />
                </div>
              </div>
            ))}
          </div>
        </div>
        <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2 outline-none" />
      </TooltipPrimitive.Provider>
    </ToastPrimitive.Provider>
  );
}
