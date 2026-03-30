from __future__ import annotations

from collections.abc import Iterable

from europeya_matrix_redactor.dto import RedactionMode, SenderScopeStatus


class SenderScopeVerifier:
    def __init__(self, repository) -> None:
        self.repository = repository

    def verify_senders(
        self,
        sender_ids: Iterable[str],
        now_ms: int,
    ) -> dict[str, SenderScopeStatus]:
        normalized_sender_ids = tuple(sorted(set(sender_ids)))
        profiles = self.repository.get_sender_profiles(normalized_sender_ids)
        tokens_by_sender = self.repository.get_sender_tokens(normalized_sender_ids, now_ms)
        statuses: dict[str, SenderScopeStatus] = {}

        for sender_id in normalized_sender_ids:
            profile = profiles.get(sender_id)
            is_local = profile is not None
            is_active = bool(profile and not profile["deactivated"])
            has_access_token = bool(tokens_by_sender.get(sender_id))

            failure_reason = None
            if not is_local:
                failure_reason = "remote_user_unsupported"
            elif not is_active:
                failure_reason = "local_user_deactivated"
            elif not has_access_token:
                failure_reason = "no_valid_access_token"

            statuses[sender_id] = SenderScopeStatus(
                user_id=sender_id,
                is_local=is_local,
                is_active=is_active,
                has_access_token=has_access_token,
                mode=RedactionMode.LOCAL_USER_ACCESS_TOKEN.value,
                failure_reason=failure_reason,
            )

        return statuses
