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
import { t } from "../i18n";

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
      <Field label={t("kitGallery.titleFieldLabel")} htmlFor="gallery-input">
        <Input id="gallery-input" defaultValue="" />
      </Field>
      <Field label={t("kitGallery.descriptionFieldLabel")} htmlFor="gallery-textarea">
        <Textarea id="gallery-textarea" defaultValue="" />
      </Field>
      <Input
        disabled
        placeholder={t("kitGallery.disabledPlaceholder")}
        aria-label={t("kitGallery.disabledFieldAria")}
      />
      <Checkbox
        aria-label={t("kitGallery.checkboxAria")}
        checked={checked}
        onCheckedChange={setChecked}
      />
      <Radio.Group
        aria-label={t("kitGallery.roleAria")}
        value={radioValue}
        onValueChange={setRadioValue}
      >
        <Radio.Item value="lecteur">{t("kitGallery.readerOption")}</Radio.Item>
        <Radio.Item value="editeur">{t("kitGallery.editorOption")}</Radio.Item>
      </Radio.Group>
      <Switch
        aria-label={t("kitGallery.activateAria")}
        checked={switchOn}
        onCheckedChange={setSwitchOn}
      />
      <Slider
        aria-label={t("kitGallery.opacityAria")}
        value={sliderValue}
        onValueChange={setSliderValue}
      />
      <Segmented
        aria-label={t("kitGallery.methodAria")}
        value={segmentedValue}
        onValueChange={setSegmentedValue}
        options={[
          { value: "quantile", label: t("kitGallery.quantileOption") },
          { value: "jenks", label: "Jenks" },
        ]}
      />
      <ColorField
        aria-label={t("kitGallery.accentColorAria")}
        value={color}
        onValueChange={setColor}
      />
      <NumberField aria-label={t("kitGallery.zoomAria")} value={number} onValueChange={setNumber} />
      <Select
        aria-label={t("kitGallery.formatAria")}
        value={selectValue}
        onValueChange={setSelectValue}
        options={[
          { value: "a", label: t("kitGallery.optionALabel") },
          { value: "b", label: t("kitGallery.optionBLabel") },
        ]}
      />
      <Combobox
        aria-label={t("kitGallery.collectionAria")}
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
          {
            value: "info",
            label: t("kitGallery.infoTabLabel"),
            content: <p>{t("kitGallery.tabContent")}</p>,
          },
          {
            value: "perms",
            label: t("kitGallery.permissionsTabLabel"),
            content: <p>{t("kitGallery.tabContent")}</p>,
          },
        ]}
      />
      <Tree
        nodes={[
          {
            id: "a",
            label: t("kitGallery.treeCartesLabel"),
            children: [{ id: "a-1", label: t("kitGallery.sampleMapLabel") }],
          },
        ]}
      />
      <Table>
        <Table.Head columns={[t("kitGallery.nameColumn"), t("catalog.typeLabel")]} />
        <tbody>
          <Table.Row>
            <Table.Cell>{t("kitGallery.sampleMapLabel")}</Table.Cell>
            <Table.Cell>map</Table.Cell>
          </Table.Row>
        </tbody>
      </Table>
      <DataTable
        columns={[
          {
            key: "name",
            label: t("kitGallery.nameColumn"),
            render: (r: { name: string }) => r.name,
          },
        ]}
        rows={[{ name: t("kitGallery.sampleMapLabel") }]}
        getRowId={(r) => r.name}
      />
      <Panel>
        <Section title={t("kitGallery.sectionTitle")}>
          <p className="text-sm text-ink">{t("kitGallery.sectionContent")}</p>
        </Section>
      </Panel>
      <Breadcrumb
        items={[
          { label: t("domain.catalog"), href: "/" },
          { label: t("kitGallery.sampleMapLabel") },
        ]}
      />
      <Toolbar.Root aria-label={t("actions.menu")}>
        <Toolbar.Button onClick={() => {}}>{t("kitGallery.measureLabel")}</Toolbar.Button>
        <Toolbar.Separator />
        <Toolbar.Button onClick={() => {}} disabled>
          {t("kitGallery.sketchLabel")}
        </Toolbar.Button>
      </Toolbar.Root>
      <div className="h-32">
        <Splitter
          first={<div>{t("kitGallery.leftLabel")}</div>}
          second={<div>{t("kitGallery.rightLabel")}</div>}
        />
      </div>
      <Popover trigger={<Button variant="outline">{t("kitGallery.openPopover")}</Button>}>
        {t("kitGallery.popoverContent")}
      </Popover>
      <Menu
        trigger={<Button variant="outline">{t("kitGallery.menuTrigger")}</Button>}
        items={[
          { label: t("actions.edit"), onSelect: () => {} },
          { label: t("actions.delete"), onSelect: () => {}, danger: true },
        ]}
      />
      <Tooltip content={t("kitGallery.tooltipContent")}>
        <IconButton icon={<span>?</span>} aria-label={t("kitGallery.helpAria")} size="sm" />
      </Tooltip>
      <Button onClick={() => setConfirmOpen(true)}>{t("kitGallery.openConfirmDialog")}</Button>
      <ConfirmDialog
        open={confirmOpen}
        title={t("actions.delete")}
        message={t("kitGallery.confirmDeleteMessage")}
        confirmLabel={t("actions.delete")}
        onConfirm={() => setConfirmOpen(false)}
        onCancel={() => setConfirmOpen(false)}
      />
      <Button onClick={() => setDrawerOpen(true)}>{t("kitGallery.openDrawer")}</Button>
      <Drawer open={drawerOpen} onOpenChange={setDrawerOpen} title={t("kitGallery.explorerTitle")}>
        <p className="text-sm text-ink">{t("kitGallery.panelContent")}</p>
      </Drawer>
      <Button onClick={() => setToastOpen(true)}>{t("kitGallery.triggerToast")}</Button>
      <Toast
        open={toastOpen}
        onOpenChange={setToastOpen}
        title={t("kitGallery.toastTitle")}
        description="OK"
      />
      <Badge variant="ok">{t("kitGallery.publishedBadge")}</Badge>
      <Chip onRemove={() => {}}>type: map</Chip>
      <Skeleton className="h-4 w-32" />
      <Spinner aria-label={t("kitGallery.loadingAria")} />
      <Progress aria-label={t("kitGallery.importAria")} value={40} />
      <EmptyState
        title={t("kitGallery.emptyTitle")}
        description={t("kitGallery.emptyDescription")}
      />
      <Banner variant="warn">{t("kitGallery.warningBanner")}</Banner>
      <Avatar alt="Tanguy" fallback="TL" />
      <Kbd>⌘K</Kbd>
      <Gate
        on={{ permissions: { read: true, write: false, delete: false, share: false } }}
        can="write"
      >
        <Button>{t("kitGallery.lockedActionLabel")}</Button>
      </Gate>
    </div>
  );
}

export function KitGalleryPage() {
  const meQuery = useMe();
  const [theme, setTheme] = useState<"light" | "dark" | undefined>(undefined);

  if (meQuery.isLoading) {
    return <p role="status">{t("common.loading")}</p>;
  }
  if (meQuery.data?.role.slug !== "admin") {
    return (
      <p role="alert" className="text-sm text-danger">
        {t("kitGallery.adminOnly")}
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
            <h1 className="text-lg font-bold text-ink">{t("kitGallery.pageTitle")}</h1>
            <Button onClick={toggleTheme}>
              {theme === "dark" ? t("kitGallery.lightThemeLabel") : t("kitGallery.darkThemeLabel")}
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
