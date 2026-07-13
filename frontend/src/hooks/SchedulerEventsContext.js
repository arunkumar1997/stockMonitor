/**
 * Context handle for the SchedulerEventsProvider store.
 *
 * Kept in its own file so React Fast Refresh can HMR the provider
 * component and the hooks without tearing down the context reference.
 */

import { createContext } from "react";

export const SchedulerEventsContext = createContext(null);
