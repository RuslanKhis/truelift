// Lint gate (frontend-quality.md): react-hooks `recommended` (7.x includes the compiler-derived
// rules) plus typescript-eslint. SB10: no dangerouslySetInnerHTML anywhere.
import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['src/client/**', 'node_modules/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  reactHooks.configs.flat.recommended,
  { files: ['public/**/*.js'], languageOptions: { globals: globals.browser, sourceType: 'script' } },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'SB10: render server text as text.',
        },
        {
          selector: "MemberExpression[property.name=/^(innerHTML|outerHTML)$/]",
          message: 'SB10: render server text as text.',
        },
      ],
    },
  },
);
