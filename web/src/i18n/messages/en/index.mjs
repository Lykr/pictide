import common from './common.json' with { type: 'json' };
import feed from './feed.json' with { type: 'json' };
import controllers from './controllers.json' with { type: 'json' };
import editor from './editor.json' with { type: 'json' };
import components from './components.json' with { type: 'json' };
export default { ...common, ...feed, ...controllers, ...editor, ...components };
