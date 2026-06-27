import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import prettierConfig from 'eslint-config-prettier'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'src/contracts/*.ts', '!src/contracts/validate.ts', '!src/contracts/validate.test.ts']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      prettierConfig,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
  {
    // shadcn/ui primitives co-export their `cva` variants, and the theme provider
    // co-exports the `useTheme` hook, alongside their components. These are vendored,
    // rarely-edited files, so the react-refresh fast-refresh constraint doesn't apply.
    files: ['src/components/ui/**/*.tsx', 'src/components/theme.tsx'],
    rules: {
      'react-refresh/only-export-components': 'off',
    },
  },
])
