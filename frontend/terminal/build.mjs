import esbuild from "esbuild";

/** 替换可选依赖为空模块（如 Ink 的 react-devtools-core） */
const optionalDepsPlugin = {
  name: "optional-deps",
  setup(build) {
    build.onResolve({ filter: /^react-devtools-core$/ }, () => ({
      path: "react-devtools-core",
      namespace: "optional-deps",
    }));
    build.onLoad({ filter: /.*/, namespace: "optional-deps" }, () => ({
      contents: "export default {}",
    }));
  },
};

await esbuild.build({
  entryPoints: ["src/index.tsx"],
  bundle: true,
  platform: "node",
  target: "node18",
  format: "esm",
  outfile: "dist/index.mjs",
  packages: "bundle",
  plugins: [optionalDepsPlugin],
  sourcemap: false,
  legalComments: "none",
  banner: {
    js: [
      'import { createRequire as __createRequire } from "node:module";',
      "const require = __createRequire(import.meta.url);",
    ].join("\n"),
  },
});
