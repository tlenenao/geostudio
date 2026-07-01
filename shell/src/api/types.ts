export type ResourceType = "app" | "dashboard" | "map";

export type CreateKind = "app" | "dashboard";

export type Item = {
  pk: string;
  resourceType: ResourceType;
  title: string;
  abstract: string;
  owner: string;
  thumbnailUrl: string | null;
  date: string;
  configId: string | null;
};

export type ItemPage = {
  items: Item[];
  total: number;
  page: number;
  pageSize: number;
};

export type Me = {
  username: string;
  firstName: string;
  lastName: string;
};

export type ListItemsParams = {
  q?: string;
  type?: ResourceType;
  page?: number;
  pageSize?: number;
};

export type UpdatePatch = { title?: string; abstract?: string; keywords?: string[] };

export type Group = { id: string; title: string };
export type ShareRole = "viewer" | "editor";
export type Sharing = {
  public: boolean;
  groups: { groupId: string; role: ShareRole }[];
};

export interface ItemClient {
  listItems(params?: ListItemsParams): Promise<ItemPage>;
  getItem(pk: string): Promise<Item>;
  getMe(): Promise<Me>;
  createConfigItem(input: { kind: CreateKind; title: string; owner: string }): Promise<Item>;
  updateItem(pk: string, patch: UpdatePatch): Promise<Item>;
  uploadThumbnail(pk: string, file: File): Promise<void>;
  deleteItem(pk: string): Promise<void>;
  listGroups(): Promise<Group[]>;
  getSharing(pk: string): Promise<Sharing>;
  setSharing(pk: string, sharing: Sharing): Promise<void>;
}
