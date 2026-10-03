// SPDX-License-Identifier: Apache-2.0
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible";
import { ChevronRight } from "lucide-react";
import { useId, useState } from "react";
import { cn } from "../../lib/utils";

export type TreeNode = {
  id: string;
  label: string;
  children?: TreeNode[];
};

// Patron ARIA tree/treeitem (P33.19) : chaque nœud est un `treeitem` (niveau,
// état déplié/sélectionné) ; le <button> reste l'élément interactif à
// l'intérieur, et les enfants d'un parent sont un `group`.
function TreeNodeRow({
  node,
  depth,
  selectedId,
  onSelect,
}: {
  node: TreeNode;
  depth: number;
  selectedId?: string;
  onSelect?: (id: string) => void;
}) {
  const hasChildren = (node.children?.length ?? 0) > 0;
  const paddingLeft = depth * 16;
  const [open, setOpen] = useState(false);
  const labelId = useId();

  if (!hasChildren) {
    return (
      <div role="treeitem" aria-level={depth + 1} aria-selected={selectedId === node.id}>
        <button
          type="button"
          onClick={() => onSelect?.(node.id)}
          style={{ paddingLeft: paddingLeft + 20 }}
          className={cn(
            "flex w-full items-center rounded-sm py-1 text-left text-sm text-ink hover:bg-sunken",
            selectedId === node.id && "bg-accent-soft text-accent-ink",
          )}
        >
          {node.label}
        </button>
      </div>
    );
  }

  return (
    <CollapsiblePrimitive.Root open={open} onOpenChange={setOpen} asChild>
      <div
        role="treeitem"
        aria-level={depth + 1}
        aria-expanded={open}
        aria-labelledby={labelId}
        aria-selected={false}
      >
        <CollapsiblePrimitive.Trigger
          id={labelId}
          style={{ paddingLeft }}
          className="flex w-full items-center gap-1 rounded-sm py-1 text-left text-sm font-medium text-ink hover:bg-sunken [&[data-state=open]>svg]:rotate-90"
        >
          <ChevronRight size={14} className="transition-transform" />
          {node.label}
        </CollapsiblePrimitive.Trigger>
        <CollapsiblePrimitive.Content role="group">
          {node.children!.map((child) => (
            <TreeNodeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </CollapsiblePrimitive.Content>
      </div>
    </CollapsiblePrimitive.Root>
  );
}

export function Tree({
  nodes,
  selectedId,
  onSelect,
}: {
  nodes: TreeNode[];
  selectedId?: string;
  onSelect?: (id: string) => void;
}) {
  return (
    <div role="tree" className="flex flex-col">
      {nodes.map((node) => (
        <TreeNodeRow
          key={node.id}
          node={node}
          depth={0}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
