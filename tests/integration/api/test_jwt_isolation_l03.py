"""L-03 E2E Integration Suite: Multi-Tenant JWT Native Isolation (S5a.1).

Validates Gate L-03 against Agno 2.8.7 native AuthMiddleware + user_isolation.
Proves that two tenants on the same instance have zero cross-tenant leaks (D-F1-11),
even when users share the same principal_id ("alice").

Matrix cases in this file:
- T1: Disjoint session buckets per composite (task 3.1)
- T2: Cross-tenant session 404 native masking (task 3.2)
- T3: Memory isolation between tenants (task 3.3)
- T4: Cross-tenant run 404 native masking (task 3.4)
- T5: Admin with agent_os:admin scope sees sessions across all tenants (task 3.5)
- T6: Dev-header mode regression (task 3.6)
- T7: Auth negatives (task 3.7)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.integration]


class TestJwtIsolationL03:
    """L-03 Gate validation test suite."""

    def test_t1_disjoint_session_buckets(
        self,
        l03_client: TestClient,
        alice_a_headers: dict[str, str],
        alice_b_headers: dict[str, str],
    ) -> None:
        """T1: Same principal 'alice' in tenants A and B gets disjoint session buckets."""
        # 1. Execute run as alice under tenant-a
        run_resp_a = l03_client.post(
            "/agents/l03-agent/runs",
            data={"message": "Session from tenant A", "stream": "false"},
            headers=alice_a_headers,
        )
        assert run_resp_a.status_code == 200, run_resp_a.text
        run_data_a = run_resp_a.json()
        session_id_a = run_data_a.get("session_id")
        assert session_id_a is not None
        assert run_data_a.get("user_id") == "tenant-a:alice"

        # 2. List sessions as alice under tenant-a -> should contain session_id_a
        sess_resp_a = l03_client.get("/sessions", headers=alice_a_headers)
        assert sess_resp_a.status_code == 200
        sess_data_a = sess_resp_a.json()
        assert sess_data_a["meta"]["total_count"] == 1
        sessions_a = sess_data_a["data"]
        assert len(sessions_a) == 1
        assert sessions_a[0]["session_id"] == session_id_a
        assert sessions_a[0]["user_id"] == "tenant-a:alice"

        # 3. List sessions as alice under tenant-b -> bucket must be empty (disjoint)
        sess_resp_b = l03_client.get("/sessions", headers=alice_b_headers)
        assert sess_resp_b.status_code == 200
        sess_data_b = sess_resp_b.json()
        assert sess_data_b["meta"]["total_count"] == 0
        assert sess_data_b["data"] == []

        # 4. Execute run as alice under tenant-b
        run_resp_b = l03_client.post(
            "/agents/l03-agent/runs",
            data={"message": "Session from tenant B", "stream": "false"},
            headers=alice_b_headers,
        )
        assert run_resp_b.status_code == 200, run_resp_b.text
        run_data_b = run_resp_b.json()
        session_id_b = run_data_b.get("session_id")
        assert session_id_b is not None
        assert session_id_b != session_id_a
        assert run_data_b.get("user_id") == "tenant-b:alice"

        # 5. List sessions as alice under tenant-b -> contains only session_id_b
        sess_resp_b2 = l03_client.get("/sessions", headers=alice_b_headers)
        assert sess_resp_b2.status_code == 200
        sess_data_b2 = sess_resp_b2.json()
        assert sess_data_b2["meta"]["total_count"] == 1
        sessions_b2 = sess_data_b2["data"]
        assert len(sessions_b2) == 1
        assert sessions_b2[0]["session_id"] == session_id_b
        assert sessions_b2[0]["user_id"] == "tenant-b:alice"

        # 6. Re-verify alice under tenant-a still only sees session_id_a
        sess_resp_a2 = l03_client.get("/sessions", headers=alice_a_headers)
        assert sess_resp_a2.status_code == 200
        sess_data_a2 = sess_resp_a2.json()
        assert sess_data_a2["meta"]["total_count"] == 1
        sessions_a2 = sess_data_a2["data"]
        assert len(sessions_a2) == 1
        assert sessions_a2[0]["session_id"] == session_id_a
        assert sessions_a2[0]["user_id"] == "tenant-a:alice"

    def test_t2_cross_tenant_session_404(
        self,
        l03_client: TestClient,
        alice_a_headers: dict[str, str],
        alice_b_headers: dict[str, str],
    ) -> None:
        """T2: Alice under tenant-b reading tenant-a's session_id receives 404 (native masking)."""
        # 1. Create a session as alice under tenant-a
        run_resp_a = l03_client.post(
            "/agents/l03-agent/runs",
            data={"message": "Confidential tenant A message", "stream": "false"},
            headers=alice_a_headers,
        )
        assert run_resp_a.status_code == 200, run_resp_a.text
        session_id_a = run_resp_a.json().get("session_id")
        assert session_id_a is not None

        # 2. alice under tenant-a can read her own session -> 200
        get_resp_a = l03_client.get(
            f"/sessions/{session_id_a}",
            headers=alice_a_headers,
        )
        assert get_resp_a.status_code == 200
        assert get_resp_a.json()["session_id"] == session_id_a
        assert get_resp_a.json()["user_id"] == "tenant-a:alice"

        # 3. alice under tenant-b attempts to read tenant-a's session -> 404
        get_resp_b = l03_client.get(
            f"/sessions/{session_id_a}",
            headers=alice_b_headers,
        )
        assert get_resp_b.status_code == 404
        error_detail = get_resp_b.json().get("detail", "")
        assert "not found" in error_detail.lower()

    def test_t3_memory_isolation(
        self,
        l03_client: TestClient,
        alice_a_headers: dict[str, str],
        alice_b_headers: dict[str, str],
    ) -> None:
        """T3: Alice under tenant-a creates memory; tenant-b listing is empty and direct read is 404.

        In Agno 2.8.7, native user-scoped memories are managed via the `/memories` router
        (POST /memories, GET /memories, GET /memories/{memory_id}).
        """
        # 1. Alice in tenant-a creates a user memory
        create_resp_a = l03_client.post(
            "/memories",
            json={"memory": "Alice secret preference under Tenant A"},
            headers=alice_a_headers,
        )
        assert create_resp_a.status_code == 200, create_resp_a.text
        mem_data_a = create_resp_a.json()
        memory_id_a = mem_data_a.get("memory_id")
        assert memory_id_a is not None
        assert mem_data_a.get("user_id") == "tenant-a:alice"

        # 2. Alice in tenant-a lists memories -> sees memory_id_a
        list_resp_a = l03_client.get("/memories", headers=alice_a_headers)
        assert list_resp_a.status_code == 200
        list_data_a = list_resp_a.json()
        assert list_data_a["meta"]["total_count"] == 1
        assert len(list_data_a["data"]) == 1
        assert list_data_a["data"][0]["memory_id"] == memory_id_a
        assert list_data_a["data"][0]["user_id"] == "tenant-a:alice"

        # 3. Alice in tenant-b lists memories -> empty list (disjoint bucket)
        list_resp_b = l03_client.get("/memories", headers=alice_b_headers)
        assert list_resp_b.status_code == 200
        list_data_b = list_resp_b.json()
        assert list_data_b["meta"]["total_count"] == 0
        assert list_data_b["data"] == []

        # 4. Alice in tenant-a reads her own memory by ID -> 200
        get_resp_a = l03_client.get(f"/memories/{memory_id_a}", headers=alice_a_headers)
        assert get_resp_a.status_code == 200
        assert get_resp_a.json()["memory_id"] == memory_id_a
        assert get_resp_a.json()["user_id"] == "tenant-a:alice"

        # 5. Alice in tenant-b attempts to read tenant-a's memory by ID -> 404
        get_resp_b = l03_client.get(f"/memories/{memory_id_a}", headers=alice_b_headers)
        assert get_resp_b.status_code == 404
        error_detail = get_resp_b.json().get("detail", "")
        assert "not found" in error_detail.lower()

        # 6. Alice in tenant-b creates her own memory
        create_resp_b = l03_client.post(
            "/memories",
            json={"memory": "Alice preference under Tenant B"},
            headers=alice_b_headers,
        )
        assert create_resp_b.status_code == 200, create_resp_b.text
        mem_data_b = create_resp_b.json()
        memory_id_b = mem_data_b.get("memory_id")
        assert memory_id_b is not None
        assert memory_id_b != memory_id_a
        assert mem_data_b.get("user_id") == "tenant-b:alice"

        # 7. Alice in tenant-b lists memories -> contains only memory_id_b
        list_resp_b2 = l03_client.get("/memories", headers=alice_b_headers)
        assert list_resp_b2.status_code == 200
        list_data_b2 = list_resp_b2.json()
        assert list_data_b2["meta"]["total_count"] == 1
        assert len(list_data_b2["data"]) == 1
        assert list_data_b2["data"][0]["memory_id"] == memory_id_b
        assert list_data_b2["data"][0]["user_id"] == "tenant-b:alice"

        # 8. Alice in tenant-a lists memories -> still contains only memory_id_a
        list_resp_a2 = l03_client.get("/memories", headers=alice_a_headers)
        assert list_resp_a2.status_code == 200
        list_data_a2 = list_resp_a2.json()
        assert list_data_a2["meta"]["total_count"] == 1
        assert len(list_data_a2["data"]) == 1
        assert list_data_a2["data"][0]["memory_id"] == memory_id_a
        assert list_data_a2["data"][0]["user_id"] == "tenant-a:alice"

    def test_t4_cross_tenant_run_404(
        self,
        l03_client: TestClient,
        alice_a_headers: dict[str, str],
        alice_b_headers: dict[str, str],
    ) -> None:
        """T4: Alice under tenant-b reading tenant-a's run_id receives 404 (native masking).

        Validates both run lookup surfaces in Agno 2.8.7:
        1. /agents/{agent_id}/runs/{run_id}?session_id={session_id}
        2. /sessions/{session_id}/runs/{run_id} and /sessions/{session_id}/runs
        """
        # 1. Execute run as alice under tenant-a
        run_resp_a = l03_client.post(
            "/agents/l03-agent/runs",
            data={"message": "Confidential run for tenant A", "stream": "false"},
            headers=alice_a_headers,
        )
        assert run_resp_a.status_code == 200, run_resp_a.text
        run_data_a = run_resp_a.json()
        run_id_a = run_data_a.get("run_id")
        session_id_a = run_data_a.get("session_id")
        assert run_id_a is not None
        assert session_id_a is not None
        assert run_data_a.get("user_id") == "tenant-a:alice"

        # 2. alice under tenant-a can read her own run via /agents/{agent_id}/runs/{run_id} -> 200
        agent_run_resp_a = l03_client.get(
            f"/agents/l03-agent/runs/{run_id_a}?session_id={session_id_a}",
            headers=alice_a_headers,
        )
        assert agent_run_resp_a.status_code == 200
        assert agent_run_resp_a.json()["run_id"] == run_id_a

        # 3. alice under tenant-a can read her own run via /sessions/{session_id}/runs/{run_id} -> 200
        sess_run_resp_a = l03_client.get(
            f"/sessions/{session_id_a}/runs/{run_id_a}",
            headers=alice_a_headers,
        )
        assert sess_run_resp_a.status_code == 200
        assert sess_run_resp_a.json()["run_id"] == run_id_a

        # 4. alice under tenant-b attempts to read tenant-a's run via /agents/{agent_id}/runs/{run_id} -> 404
        agent_run_resp_b = l03_client.get(
            f"/agents/l03-agent/runs/{run_id_a}?session_id={session_id_a}",
            headers=alice_b_headers,
        )
        assert agent_run_resp_b.status_code == 404
        error_detail_agent = agent_run_resp_b.json().get("detail", "")
        assert "not found" in error_detail_agent.lower()

        # 5. alice under tenant-b attempts to read tenant-a's run via /sessions/{session_id}/runs/{run_id} -> 404
        sess_run_resp_b = l03_client.get(
            f"/sessions/{session_id_a}/runs/{run_id_a}",
            headers=alice_b_headers,
        )
        assert sess_run_resp_b.status_code == 404
        error_detail_sess = sess_run_resp_b.json().get("detail", "")
        assert "not found" in error_detail_sess.lower()

        # 6. alice under tenant-b attempts to list runs via /sessions/{session_id}/runs -> 404
        sess_runs_list_b = l03_client.get(
            f"/sessions/{session_id_a}/runs",
            headers=alice_b_headers,
        )
        assert sess_runs_list_b.status_code == 404
        assert "not found" in sess_runs_list_b.json().get("detail", "").lower()

    def test_t5_admin_sees_all(
        self,
        l03_client: TestClient,
        alice_a_headers: dict[str, str],
        alice_b_headers: dict[str, str],
        admin_headers: dict[str, str],
    ) -> None:
        """T5: Admin token with agent_os:admin scope lists sessions across all tenants."""
        # 1. Execute run as alice under tenant-a
        run_resp_a = l03_client.post(
            "/agents/l03-agent/runs",
            data={"message": "Tenant A session for admin test", "stream": "false"},
            headers=alice_a_headers,
        )
        assert run_resp_a.status_code == 200, run_resp_a.text
        session_id_a = run_resp_a.json().get("session_id")
        assert session_id_a is not None

        # 2. Execute run as alice under tenant-b
        run_resp_b = l03_client.post(
            "/agents/l03-agent/runs",
            data={"message": "Tenant B session for admin test", "stream": "false"},
            headers=alice_b_headers,
        )
        assert run_resp_b.status_code == 200, run_resp_b.text
        session_id_b = run_resp_b.json().get("session_id")
        assert session_id_b is not None
        assert session_id_b != session_id_a

        # 3. Alice under tenant-a lists sessions -> sees only session_id_a
        sess_resp_a = l03_client.get("/sessions", headers=alice_a_headers)
        assert sess_resp_a.status_code == 200
        sess_data_a = sess_resp_a.json()
        assert sess_data_a["meta"]["total_count"] == 1
        assert [s["session_id"] for s in sess_data_a["data"]] == [session_id_a]
        assert [s["user_id"] for s in sess_data_a["data"]] == ["tenant-a:alice"]

        # 4. Alice under tenant-b lists sessions -> sees only session_id_b
        sess_resp_b = l03_client.get("/sessions", headers=alice_b_headers)
        assert sess_resp_b.status_code == 200
        sess_data_b = sess_resp_b.json()
        assert sess_data_b["meta"]["total_count"] == 1
        assert [s["session_id"] for s in sess_data_b["data"]] == [session_id_b]
        assert [s["user_id"] for s in sess_data_b["data"]] == ["tenant-b:alice"]

        # 5. Admin lists sessions -> sees BOTH tenant-a and tenant-b sessions
        sess_resp_admin = l03_client.get("/sessions", headers=admin_headers)
        assert sess_resp_admin.status_code == 200
        sess_data_admin = sess_resp_admin.json()
        assert sess_data_admin["meta"]["total_count"] == 2
        admin_sess_ids = {s["session_id"] for s in sess_data_admin["data"]}
        assert session_id_a in admin_sess_ids
        assert session_id_b in admin_sess_ids
        admin_user_ids = {s["user_id"] for s in sess_data_admin["data"]}
        assert admin_user_ids == {"tenant-a:alice", "tenant-b:alice"}

        # 6. Admin can read individual sessions from both tenants directly
        get_admin_a = l03_client.get(f"/sessions/{session_id_a}", headers=admin_headers)
        assert get_admin_a.status_code == 200
        assert get_admin_a.json()["session_id"] == session_id_a

        get_admin_b = l03_client.get(f"/sessions/{session_id_b}", headers=admin_headers)
        assert get_admin_b.status_code == 200
        assert get_admin_b.json()["session_id"] == session_id_b

    def test_t6_dev_header_regression(
        self,
        l03_dev_client: TestClient,
    ) -> None:
        """T6: Dev-header mode (authorization=False, mount_tenant_context=True) path regression.

        Proves that without JWT auth, requests carrying X-Tenant-Id header correctly resolve
        composite user_id via resolve_user_id() (SPEC_06 §3.2 dev contract), write sessions
        attributed to that composite, allow filtered reads by composite, and reject requests
        lacking the X-Tenant-Id header with 401.
        """
        # 1. Execute run as tenant-a without JWT
        run_resp_a = l03_dev_client.post(
            "/agents/l03-agent/runs",
            data={"message": "Dev session for tenant A", "stream": "false"},
            headers={"X-Tenant-Id": "tenant-a"},
        )
        assert run_resp_a.status_code == 200, run_resp_a.text
        run_data_a = run_resp_a.json()
        session_id_a = run_data_a.get("session_id")
        assert session_id_a is not None
        assert run_data_a.get("user_id") == "tenant-a:alice"

        # 2. Execute run as tenant-b without JWT
        run_resp_b = l03_dev_client.post(
            "/agents/l03-agent/runs",
            data={"message": "Dev session for tenant B", "stream": "false"},
            headers={"X-Tenant-Id": "tenant-b"},
        )
        assert run_resp_b.status_code == 200, run_resp_b.text
        run_data_b = run_resp_b.json()
        session_id_b = run_data_b.get("session_id")
        assert session_id_b is not None
        assert session_id_b != session_id_a
        assert run_data_b.get("user_id") == "tenant-b:alice"

        # 3. Filter sessions for tenant-a:alice -> sees only session_id_a
        sess_resp_a = l03_dev_client.get(
            "/sessions?user_id=tenant-a:alice",
            headers={"X-Tenant-Id": "tenant-a"},
        )
        assert sess_resp_a.status_code == 200
        sess_data_a = sess_resp_a.json()
        assert sess_data_a["meta"]["total_count"] == 1
        assert [s["session_id"] for s in sess_data_a["data"]] == [session_id_a]
        assert [s["user_id"] for s in sess_data_a["data"]] == ["tenant-a:alice"]

        # 4. Filter sessions for tenant-b:alice -> sees only session_id_b
        sess_resp_b = l03_dev_client.get(
            "/sessions?user_id=tenant-b:alice",
            headers={"X-Tenant-Id": "tenant-b"},
        )
        assert sess_resp_b.status_code == 200
        sess_data_b = sess_resp_b.json()
        assert sess_data_b["meta"]["total_count"] == 1
        assert [s["session_id"] for s in sess_data_b["data"]] == [session_id_b]
        assert [s["user_id"] for s in sess_data_b["data"]] == ["tenant-b:alice"]

        # 5. Direct session read with X-Tenant-Id header succeeds
        get_resp_a = l03_dev_client.get(f"/sessions/{session_id_a}", headers={"X-Tenant-Id": "tenant-a"})
        assert get_resp_a.status_code == 200
        assert get_resp_a.json()["session_id"] == session_id_a
        assert get_resp_a.json()["user_id"] == "tenant-a:alice"

        # 6. Request without X-Tenant-Id header returns 401 (TenantContextMiddleware guard)
        no_hdr_resp = l03_dev_client.get("/sessions")
        assert no_hdr_resp.status_code == 401
        assert "tenant_id is required" in no_hdr_resp.json().get("detail", "")
