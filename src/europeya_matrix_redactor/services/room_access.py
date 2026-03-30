from __future__ import annotations

from collections.abc import Iterable

from europeya_matrix_redactor.dto import RedactionMode, SenderScopeStatus


class SenderScopeVerifier:
    def __init__(self, repository) -> None:
        self.repository = repository

    def verify_senders(
        self,
        sender_ids: Iterable[str],
    ) -> dict[str, SenderScopeStatus]:
        normalized_sender_ids = tuple(sorted(set(sender_ids)))
        profiles = self.repository.get_sender_profiles(normalized_sender_ids)
        statuses: dict[str, SenderScopeStatus] = {}

        for sender_id in normalized_sender_ids:
            profile = profiles.get(sender_id)
            is_local = profile is not None
            is_active = bool(profile and not profile["deactivated"])

            failure_reason = None
            if not is_local:
                failure_reason = "remote_user_unsupported"
            elif not is_active:
                failure_reason = "local_user_deactivated"

            statuses[sender_id] = SenderScopeStatus(
                user_id=sender_id,
                is_local=is_local,
                is_active=is_active,
                mode=RedactionMode.LOCAL_USER_IMPERSONATION.value,
                failure_reason=failure_reason,
            )

        return statuses
