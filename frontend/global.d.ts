/// <reference types="next" />
/// <reference types="next/image-types/global" />

// CSS imports
declare module "*.css" {
  const content: Record<string, string>;
  export default content;
}